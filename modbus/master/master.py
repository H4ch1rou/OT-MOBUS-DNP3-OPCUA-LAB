"""
Modbus TCP master (maestro) - Central SCADA de Riego (multi-zona).

Logica de control (histeresis) por cada zona, sobre la humedad del suelo
expuesta por el RTU de campo:
  - si humedad <= umbral_min -> abre la valvula de esa zona
  - si humedad >= umbral_max -> cierra la valvula de esa zona
  - si esta entre ambos umbrales -> mantiene el estado actual

Cada zona tiene ademas una coil de "modo manual". Mientras esa coil este
en 1, este master NO escribe la valvula de esa zona: la deja
completamente en manos del HMI web / la herramienta de operador. Esto
evita el "tira y afloja" tipico cuando dos escritores (el lazo automatico
y un operador humano) compiten por el mismo actuador -- aqui se resuelve
con una bandera explicita, tal como lo haria un PLC real con un
selector local/remoto.

En cada ciclo este master LEE el estado real de las coils (valvula y modo)
en vez de confiar en una copia local: asi el comportamiento es siempre
consistente con lo que de verdad tiene el RTU, sin importar quien haya
escrito por ultima vez. Los umbrales tambien se leen del RTU en cada
ciclo, asi que cualquier cambio hecho desde el HMI web o el operador se
refleja de inmediato, y puede observarse en la red con tcpdump/Wireshark
como paquetes Modbus de escritura (FC 05/06).
"""

import logging
import os
import time

from pymodbus.client import ModbusTcpClient
from pymodbus.exceptions import ModbusException

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [SCADA-RIEGO] %(message)s",
)
log = logging.getLogger("modbus-master")

SLAVE_HOST = os.environ.get("SLAVE_HOST", "modbus-slave")
SLAVE_PORT = int(os.environ.get("SLAVE_PORT", "502"))
UNIT_ID = int(os.environ.get("UNIT_ID", "1"))
POLL_SECONDS = float(os.environ.get("POLL_SECONDS", "2"))

NOMBRES_ZONAS = [
    "Zona 1 - Parronal",
    "Zona 2 - Hortalizas",
    "Zona 3 - Frutales",
    "Zona 4 - Vivero",
]
N_ZONAS = len(NOMBRES_ZONAS)
HR_STRIDE = 10
DI_STRIDE = 2


def hr_base(zona: int) -> int:
    return zona * HR_STRIDE


def co_valvula(zona: int) -> int:
    return zona


def co_modo_manual(zona: int) -> int:
    return N_ZONAS + zona


def di_base(zona: int) -> int:
    return zona * DI_STRIDE


def connect_with_retry(client: ModbusTcpClient) -> None:
    while not client.connect():
        log.warning("no se pudo conectar al RTU %s:%s, reintentando en 3s...", SLAVE_HOST, SLAVE_PORT)
        time.sleep(3)
    log.info("conectado al RTU de riego en %s:%s (%d zonas)", SLAVE_HOST, SLAVE_PORT, N_ZONAS)


def main() -> None:
    client = ModbusTcpClient(SLAVE_HOST, port=SLAVE_PORT)
    connect_with_retry(client)

    while True:
        try:
            # Una sola lectura cubre las coils de valvula (0..N-1) y de
            # modo manual (N..2N-1) de todas las zonas.
            coils_rr = client.read_coils(0, count=2 * N_ZONAS, slave=UNIT_ID)
            if coils_rr.isError():
                raise ModbusException("no se pudieron leer las coils del RTU")

            for zona in range(N_ZONAS):
                datos_rr = client.read_holding_registers(hr_base(zona), count=4, slave=UNIT_ID)
                alarmas_rr = client.read_discrete_inputs(di_base(zona), count=2, slave=UNIT_ID)

                if datos_rr.isError() or alarmas_rr.isError():
                    raise ModbusException(f"respuesta de error del RTU en {NOMBRES_ZONAS[zona]}")

                humedad, caudal, umbral_min, umbral_max = datos_rr.registers
                alarma_baja, alarma_encharcamiento = alarmas_rr.bits[0], alarmas_rr.bits[1]
                valvula_actual = coils_rr.bits[zona]
                modo_manual = coils_rr.bits[N_ZONAS + zona]

                if modo_manual:
                    modo_txt = "MANUAL (SCADA no interviene)"
                else:
                    if humedad <= umbral_min:
                        valvula_actual = True
                    elif humedad >= umbral_max:
                        valvula_actual = False
                    client.write_coil(co_valvula(zona), valvula_actual, slave=UNIT_ID)
                    modo_txt = "AUTOMATICO"

                log.info(
                    "[%s] modo=%s humedad=%3d%% caudal=%3d L/min umbrales=[%d-%d] valvula=%-7s "
                    "alarma_baja=%s encharcamiento=%s",
                    NOMBRES_ZONAS[zona], modo_txt, humedad, caudal, umbral_min, umbral_max,
                    "ABIERTA" if valvula_actual else "CERRADA",
                    alarma_baja, alarma_encharcamiento,
                )

                if alarma_baja:
                    log.warning("ALARMA: humedad critica baja en %s (%d%%)", NOMBRES_ZONAS[zona], humedad)
                if alarma_encharcamiento:
                    log.warning("ALARMA: encharcamiento en %s (%d%%)", NOMBRES_ZONAS[zona], humedad)

        except (ModbusException, ConnectionError, OSError) as exc:
            log.error("error de comunicacion Modbus: %s", exc)
            client.close()
            connect_with_retry(client)

        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
