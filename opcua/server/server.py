"""
Servidor OPC UA de la Central de Riego (multi-zona).

Mismo proceso fisico simulado que los laboratorios Modbus y DNP3 (para
poder comparar los tres protocolos sobre el mismo escenario), expuesto
ahora como un espacio de nodos OPC UA usando `asyncua`.

Arbol de nodos (namespace propio, registrado como "http://riego.local/"):

    Objects
      Zonas
        Zona1 .. Zona4
          Humedad            (Double, solo lectura)
          Caudal             (Double, solo lectura)
          UmbralMinimo       (Double, escribible)
          UmbralMaximo       (Double, escribible)
          Valvula            (Boolean, escribible)
          ModoManual         (Boolean, escribible)
          AlarmaBaja         (Boolean, solo lectura)
          AlarmaEncharcamiento (Boolean, solo lectura)

A diferencia de Modbus (coils) y DNP3 (CROB/Analog Output command), en
OPC UA no hace falta un "objeto de comando" especial para controlar un
actuador: el cliente simplemente ESCRIBE el valor directo en la variable
`Valvula` o `ModoManual`, si su AccessLevel lo permite. Este servidor no
implementa ninguna autenticacion (SecurityPolicy = NoSecurity, sesion
anonima): igual que en los otros dos laboratorios, cualquier cliente que
llegue al puerto 4840 puede leer y escribir sin credenciales.
"""

import asyncio
import logging
import os

from asyncua import Server, ua

logging.basicConfig(level=logging.INFO, format="%(asctime)s [RTU-RIEGO-OPCUA] %(message)s")
logging.getLogger("asyncua").setLevel(logging.WARNING)
log = logging.getLogger("opcua-server")

HOST = "0.0.0.0"
PORT = int(os.environ.get("OPCUA_PORT", "4840"))
ENDPOINT = f"opc.tcp://{HOST}:{PORT}/riego/server/"
NAMESPACE_URI = "http://riego.local/"

ZONAS = [
    {"nombre": "Zona 1 - Parronal", "humedad_inicial": 55.0},
    {"nombre": "Zona 2 - Hortalizas", "humedad_inicial": 35.0},
    {"nombre": "Zona 3 - Frutales", "humedad_inicial": 65.0},
    {"nombre": "Zona 4 - Vivero", "humedad_inicial": 45.0},
]
N_ZONAS = len(ZONAS)

RIEGO_RATE = 3.0
EVAPO_RATE = 1.0
TICK_SECONDS = 1.0
UMBRAL_MIN_DEFAULT = 30.0
UMBRAL_MAX_DEFAULT = 80.0


async def crear_zonas(server: Server, idx: int, objects) -> list[dict]:
    zonas_root = await objects.add_object(idx, "Zonas")
    nodos = []

    for z in ZONAS:
        obj = await zonas_root.add_object(idx, z["nombre"].split(" - ")[0].replace(" ", ""))

        humedad = await obj.add_variable(idx, "Humedad", z["humedad_inicial"])
        caudal = await obj.add_variable(idx, "Caudal", 0.0)
        umbral_min = await obj.add_variable(idx, "UmbralMinimo", UMBRAL_MIN_DEFAULT)
        umbral_max = await obj.add_variable(idx, "UmbralMaximo", UMBRAL_MAX_DEFAULT)
        valvula = await obj.add_variable(idx, "Valvula", False)
        modo_manual = await obj.add_variable(idx, "ModoManual", False)
        alarma_baja = await obj.add_variable(idx, "AlarmaBaja", False)
        alarma_ench = await obj.add_variable(idx, "AlarmaEncharcamiento", False)

        for escribible in (umbral_min, umbral_max, valvula, modo_manual):
            await escribible.set_writable()

        nodos.append({
            "nombre": z["nombre"],
            "humedad_actual": z["humedad_inicial"],
            "humedad": humedad, "caudal": caudal,
            "umbral_min": umbral_min, "umbral_max": umbral_max,
            "valvula": valvula, "modo_manual": modo_manual,
            "alarma_baja": alarma_baja, "alarma_encharcamiento": alarma_ench,
        })

    return nodos


async def simular_proceso(zonas: list[dict]) -> None:
    while True:
        for z in zonas:
            valvula_abierta = await z["valvula"].get_value()

            if valvula_abierta:
                z["humedad_actual"] += RIEGO_RATE
            z["humedad_actual"] -= EVAPO_RATE
            z["humedad_actual"] = max(0.0, min(100.0, z["humedad_actual"]))
            caudal = RIEGO_RATE * 10 if valvula_abierta else 0.0

            await z["humedad"].write_value(z["humedad_actual"])
            await z["caudal"].write_value(caudal)

            alarma_baja = z["humedad_actual"] < 10
            alarma_ench = z["humedad_actual"] > 95
            await z["alarma_baja"].write_value(alarma_baja)
            await z["alarma_encharcamiento"].write_value(alarma_ench)

            estado = "ABIERTA" if valvula_abierta else "CERRADA"
            log.info(
                "[%s] humedad=%5.1f%% valvula=%-7s caudal=%3.0f L/min alarma_baja=%s encharcamiento=%s",
                z["nombre"], z["humedad_actual"], estado, caudal, alarma_baja, alarma_ench,
            )

        await asyncio.sleep(TICK_SECONDS)


async def main() -> None:
    server = Server()
    await server.init()
    server.set_endpoint(ENDPOINT)
    server.set_security_policy([ua.SecurityPolicyType.NoSecurity])
    server.set_server_name("RTU Simulado - Central de Riego (OPC UA)")

    idx = await server.register_namespace(NAMESPACE_URI)
    objects = server.get_objects_node()
    zonas = await crear_zonas(server, idx, objects)

    log.info("Servidor OPC UA escuchando en %s (namespace idx=%d, %d zonas)", ENDPOINT, idx, N_ZONAS)

    async with server:
        await simular_proceso(zonas)


if __name__ == "__main__":
    asyncio.run(main())
