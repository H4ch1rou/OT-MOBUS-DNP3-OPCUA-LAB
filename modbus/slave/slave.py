"""
Modbus TCP slave (esclavo) - RTU de campo de una Central de Riego con
multiples zonas/electrovalvulas.

Simula la estacion remota (RTU) instalada en un predio agricola con varias
zonas de riego, cada una con su propio sensor de humedad de suelo y su
propia electrovalvula. Expone via Modbus TCP:

  Holding Registers (FC 03 lectura / FC 06-16 escritura) - 10 registros
  por zona, direccion base = zona_idx * 10:
    base+0 - humedad del suelo actual (%)            [solo el proceso]
    base+1 - caudal instantaneo de riego (L/min)      [solo el proceso]
    base+2 - umbral MINIMO de humedad (abre valvula)  [SCADA/HMI/operador]
    base+3 - umbral MAXIMO de humedad (cierra valvula)[SCADA/HMI/operador]

  Coils (FC 01 lectura / FC 05 escritura):
    CO<zona>            - electrovalvula de la zona (abierta/cerrada)
    CO<N_ZONAS+zona>    - modo MANUAL de la zona (1=manual, 0=automatico)

  Discrete Inputs (FC 02, solo lectura) - 2 por zona, base = zona_idx * 2:
    base+0 - alarma de humedad critica baja (< 10%)
    base+1 - alarma de encharcamiento / exceso de riego (> 95%)

Un hilo en background simula la fisica del suelo de cada zona cada
segundo: si la valvula esta abierta, la humedad sube (riego); existe
evapotranspiracion constante que la hace bajar.

Los umbrales y el modo manual/automatico NO son usados por este proceso:
los lee y escribe la Central SCADA (master), el HMI web y la herramienta
de operador -- precisamente para poder observar esos cambios circulando
en la red con tcpdump/Wireshark. El RTU es "I/O tonta": no sabe nada de
umbrales ni de modos, solo expone sensores y obedece la ultima escritura
que reciba sobre la valvula, venga de quien venga.
"""

import logging
import threading
import time

from pymodbus.datastore import (
    ModbusSequentialDataBlock,
    ModbusServerContext,
    ModbusSlaveContext,
)
from pymodbus.device import ModbusDeviceIdentification
from pymodbus.server import StartTcpServer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [RTU-RIEGO] %(message)s",
)
log = logging.getLogger("modbus-slave")

# --- Definicion de zonas de riego ------------------------------------------
ZONAS = [
    {"nombre": "Zona 1 - Parronal", "humedad_inicial": 55.0},
    {"nombre": "Zona 2 - Hortalizas", "humedad_inicial": 35.0},
    {"nombre": "Zona 3 - Frutales", "humedad_inicial": 65.0},
    {"nombre": "Zona 4 - Vivero", "humedad_inicial": 45.0},
]
N_ZONAS = len(ZONAS)

HR_STRIDE = 10  # espacio reservado por zona en holding registers
DI_STRIDE = 2   # espacio reservado por zona en discrete inputs

RIEGO_RATE = 3.0        # % de humedad por segundo con la valvula abierta
EVAPO_RATE = 1.0        # % de humedad por segundo perdido por evapotranspiracion
TICK_SECONDS = 1.0

UMBRAL_MIN_DEFAULT = 30  # % humedad -> abre la valvula
UMBRAL_MAX_DEFAULT = 80  # % humedad -> cierra la valvula


def hr_humedad(zona: int) -> int:
    return zona * HR_STRIDE + 0


def hr_caudal(zona: int) -> int:
    return zona * HR_STRIDE + 1


def hr_umbral_min(zona: int) -> int:
    return zona * HR_STRIDE + 2


def hr_umbral_max(zona: int) -> int:
    return zona * HR_STRIDE + 3


def co_valvula(zona: int) -> int:
    return zona


def co_modo_manual(zona: int) -> int:
    return N_ZONAS + zona


def di_alarma_baja(zona: int) -> int:
    return zona * DI_STRIDE + 0


def di_alarma_encharcamiento(zona: int) -> int:
    return zona * DI_STRIDE + 1


# Estado inicial del proceso fisico (uno por zona)
humedad_suelo = [z["humedad_inicial"] for z in ZONAS]


def simulate_process(context: ModbusSlaveContext) -> None:
    """Hilo de fondo: simula cada zona de riego y actualiza el datastore."""
    while True:
        for zona in range(N_ZONAS):
            valvula_abierta = bool(
                context.getValues(1, co_valvula(zona), count=1)[0]  # FC 01 -> coils
            )

            if valvula_abierta:
                humedad_suelo[zona] += RIEGO_RATE
            humedad_suelo[zona] -= EVAPO_RATE
            humedad_suelo[zona] = max(0.0, min(100.0, humedad_suelo[zona]))

            caudal = RIEGO_RATE * 10 if valvula_abierta else 0

            context.setValues(3, hr_humedad(zona), [int(humedad_suelo[zona])])
            context.setValues(3, hr_caudal(zona), [int(caudal)])

            alarma_baja = humedad_suelo[zona] < 10
            alarma_encharcamiento = humedad_suelo[zona] > 95
            context.setValues(2, di_alarma_baja(zona), [alarma_baja])
            context.setValues(2, di_alarma_encharcamiento(zona), [alarma_encharcamiento])

            estado = "ABIERTA" if valvula_abierta else "CERRADA"
            log.info(
                "[%s] humedad=%5.1f%% valvula=%-7s caudal=%3d L/min alarma_baja=%s encharcamiento=%s",
                ZONAS[zona]["nombre"], humedad_suelo[zona], estado, caudal,
                alarma_baja, alarma_encharcamiento,
            )

        time.sleep(TICK_SECONDS)


def main() -> None:
    n_regs = N_ZONAS * HR_STRIDE
    n_di = N_ZONAS * DI_STRIDE
    n_coils = 2 * N_ZONAS  # valvula + modo manual, por zona

    store = ModbusSlaveContext(
        di=ModbusSequentialDataBlock(0, [0] * max(n_di, 10)),
        co=ModbusSequentialDataBlock(0, [0] * max(n_coils, 10)),
        hr=ModbusSequentialDataBlock(0, [0] * max(n_regs, 10)),
        ir=ModbusSequentialDataBlock(0, [0] * 10),
        zero_mode=True,
    )

    # Umbrales iniciales de operacion (configurables luego via SCADA/HMI/operador)
    for zona in range(N_ZONAS):
        store.setValues(3, hr_umbral_min(zona), [UMBRAL_MIN_DEFAULT])
        store.setValues(3, hr_umbral_max(zona), [UMBRAL_MAX_DEFAULT])

    context = ModbusServerContext(slaves=store, single=True)

    identity = ModbusDeviceIdentification(
        info_name={
            "VendorName": "OT-PoC-Lab",
            "ProductCode": "RIEGO-RTU",
            "ProductName": "RTU Simulado - Central de Riego (multi-zona)",
            "ModelName": "PoC Modbus Slave",
        }
    )

    threading.Thread(target=simulate_process, args=(store,), daemon=True).start()

    log.info(
        "Iniciando servidor Modbus TCP en 0.0.0.0:502 (%d zonas: %s)",
        N_ZONAS, ", ".join(z["nombre"] for z in ZONAS),
    )
    StartTcpServer(context=context, identity=identity, address=("0.0.0.0", 502))


if __name__ == "__main__":
    main()
