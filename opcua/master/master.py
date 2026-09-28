"""
Master OPC UA (Central SCADA) de la Central de Riego.

Combina DOS mecanismos, ambos nativos de OPC UA, para mostrar que este
protocolo ofrece una tercera forma de enterarse de cambios (distinta a
"solo polling" de Modbus y a las respuestas no solicitadas de DNP3):

  - `bucle_control()`: integrity-poll manual (lee todas las variables)
    cada `POLL_SECONDS`, aplica la misma logica de histeresis de los
    otros laboratorios, y escribe la valvula directamente si corresponde.
  - Una **Subscription** OPC UA sobre las variables de alarma de cada
    zona: el servidor empuja una notificacion de cambio (DataChange) en
    cuanto una alarma cambia, sin que el master tenga que pedirla. A
    diferencia de la UNSOLICITED_RESPONSE de DNP3 (que tuvimos que
    modelar a mano), esta es una funcionalidad **estandar y nativa** del
    protocolo OPC UA, con su propio mecanismo de negociacion de intervalo
    de publicacion.
"""

import asyncio
import logging
import os

from asyncua import Client, ua

logging.basicConfig(level=logging.INFO, format="%(asctime)s [SCADA-RIEGO-OPCUA] %(message)s")
logging.getLogger("asyncua").setLevel(logging.WARNING)
log = logging.getLogger("opcua-master")

SERVER_HOST = os.environ.get("SERVER_HOST", "opcua-server")
SERVER_PORT = int(os.environ.get("SERVER_PORT", "4840"))
SERVER_URL = f"opc.tcp://{SERVER_HOST}:{SERVER_PORT}/riego/server/"
NAMESPACE_URI = "http://riego.local/"
POLL_SECONDS = float(os.environ.get("POLL_SECONDS", "2"))

NOMBRES_ZONAS = [
    "Zona 1 - Parronal",
    "Zona 2 - Hortalizas",
    "Zona 3 - Frutales",
    "Zona 4 - Vivero",
]
N_ZONAS = len(NOMBRES_ZONAS)
NOMBRES_NODOS = ["Zona1", "Zona2", "Zona3", "Zona4"]


class HandlerAlarmas:
    """Se ejecuta cada vez que el servidor empuja un cambio de una de las
    variables de alarma suscritas -- sin que nadie haya hecho ningun poll."""

    def datachange_notification(self, node, val, data):
        log.warning("<- SUBSCRIPTION: %s cambio a %s [nadie hizo poll, el servidor lo empujo solo]", node, val)


async def obtener_nodos_zona(objects, idx: int, nombre_nodo: str) -> dict:
    obj = await objects.get_child([f"{idx}:Zonas", f"{idx}:{nombre_nodo}"])
    return {
        "obj": obj,
        "humedad": await obj.get_child(f"{idx}:Humedad"),
        "caudal": await obj.get_child(f"{idx}:Caudal"),
        "umbral_min": await obj.get_child(f"{idx}:UmbralMinimo"),
        "umbral_max": await obj.get_child(f"{idx}:UmbralMaximo"),
        "valvula": await obj.get_child(f"{idx}:Valvula"),
        "modo_manual": await obj.get_child(f"{idx}:ModoManual"),
        "alarma_baja": await obj.get_child(f"{idx}:AlarmaBaja"),
        "alarma_encharcamiento": await obj.get_child(f"{idx}:AlarmaEncharcamiento"),
    }


async def bucle_control(zonas: list[dict]) -> None:
    while True:
        for i, z in enumerate(zonas):
            humedad = await z["humedad"].read_value()
            caudal = await z["caudal"].read_value()
            umbral_min = await z["umbral_min"].read_value()
            umbral_max = await z["umbral_max"].read_value()
            valvula_actual = await z["valvula"].read_value()
            modo_manual = await z["modo_manual"].read_value()
            alarma_baja = await z["alarma_baja"].read_value()
            alarma_ench = await z["alarma_encharcamiento"].read_value()

            if modo_manual:
                modo_txt = "MANUAL (SCADA no interviene)"
            else:
                if humedad <= umbral_min:
                    valvula_actual = True
                elif humedad >= umbral_max:
                    valvula_actual = False
                await z["valvula"].write_value(valvula_actual)
                modo_txt = "AUTOMATICO"

            log.info(
                "[%s] modo=%s humedad=%5.1f%% caudal=%3.0f L/min umbrales=[%.0f-%.0f] valvula=%-7s "
                "alarma_baja=%s encharcamiento=%s",
                NOMBRES_ZONAS[i], modo_txt, humedad, caudal, umbral_min, umbral_max,
                "ABIERTA" if valvula_actual else "CERRADA", alarma_baja, alarma_ench,
            )

        await asyncio.sleep(POLL_SECONDS)


async def main() -> None:
    while True:
        try:
            async with Client(url=SERVER_URL) as client:
                log.info("conectado al servidor OPC UA en %s", SERVER_URL)
                idx = await client.get_namespace_index(NAMESPACE_URI)
                objects = client.get_objects_node()

                zonas = [await obtener_nodos_zona(objects, idx, nombre) for nombre in NOMBRES_NODOS]

                handler = HandlerAlarmas()
                sub = await client.create_subscription(500, handler)
                nodos_alarma = [z["alarma_baja"] for z in zonas] + [z["alarma_encharcamiento"] for z in zonas]
                await sub.subscribe_data_change(nodos_alarma)
                log.info("suscripcion activa sobre %d variables de alarma (push nativo de OPC UA)", len(nodos_alarma))

                await bucle_control(zonas)
        except (ConnectionError, OSError, asyncio.TimeoutError) as exc:
            log.error("conexion perdida (%s), reintentando en 3s...", exc)
            await asyncio.sleep(3)


if __name__ == "__main__":
    asyncio.run(main())
