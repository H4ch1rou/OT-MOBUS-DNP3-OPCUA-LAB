"""
Herramienta de operador manual para la Central de Riego OPC UA (multi-zona).

Se conecta DIRECTO como cliente OPC UA al servidor (`opcua-server`), sin
pasar por la Central SCADA (`opcua-master`) -- mismo punto de discusion
que en los otros dos laboratorios: el servidor acepta la conexion sin
verificar si eres "de verdad" el SCADA autorizado (sesion anonima, sin
seguridad).

Uso:
    docker compose run --rm opcua-operador
"""

import os

from asyncua.sync import Client

SERVER_HOST = os.environ.get("SERVER_HOST", "opcua-server")
SERVER_PORT = int(os.environ.get("SERVER_PORT", "4840"))
SERVER_URL = f"opc.tcp://{SERVER_HOST}:{SERVER_PORT}/riego/server/"
NAMESPACE_URI = "http://riego.local/"

NOMBRES_ZONAS = [
    "Zona 1 - Parronal",
    "Zona 2 - Hortalizas",
    "Zona 3 - Frutales",
    "Zona 4 - Vivero",
]
N_ZONAS = len(NOMBRES_ZONAS)
NOMBRES_NODOS = ["Zona1", "Zona2", "Zona3", "Zona4"]

MENU = """
=== Operador manual OPC UA - Central de Riego (servidor: {url}) ===
1) Ver estado de todas las zonas
2) Cambiar umbral MINIMO de humedad de una zona
3) Cambiar umbral MAXIMO de humedad de una zona
4) Forzar APERTURA manual de la valvula de una zona (pasa a modo MANUAL)
5) Forzar CIERRE manual de la valvula de una zona (pasa a modo MANUAL)
6) Devolver una zona a modo AUTOMATICO (la controla el SCADA)
0) Salir
> """


def pedir_zona() -> int | None:
    for i, nombre in enumerate(NOMBRES_ZONAS, start=1):
        print(f"  {i}) {nombre}")
    valor = input(f"  zona (1-{N_ZONAS}): ").strip()
    if not valor.isdigit() or not (1 <= int(valor) <= N_ZONAS):
        print("  [!] zona invalida")
        return None
    return int(valor) - 1


def pedir_numero(mensaje: str) -> float | None:
    valor = input(mensaje).strip()
    try:
        return float(valor)
    except ValueError:
        print("  [!] valor invalido, debe ser un numero")
        return None


def obtener_nodos_zona(objects, idx: int, nombre_nodo: str) -> dict:
    obj = objects.get_child([f"{idx}:Zonas", f"{idx}:{nombre_nodo}"])
    return {
        "humedad": obj.get_child(f"{idx}:Humedad"),
        "caudal": obj.get_child(f"{idx}:Caudal"),
        "umbral_min": obj.get_child(f"{idx}:UmbralMinimo"),
        "umbral_max": obj.get_child(f"{idx}:UmbralMaximo"),
        "valvula": obj.get_child(f"{idx}:Valvula"),
        "modo_manual": obj.get_child(f"{idx}:ModoManual"),
        "alarma_baja": obj.get_child(f"{idx}:AlarmaBaja"),
        "alarma_encharcamiento": obj.get_child(f"{idx}:AlarmaEncharcamiento"),
    }


def mostrar_estado(zonas: list[dict]) -> None:
    for i, z in enumerate(zonas):
        print(f"\n  --- {NOMBRES_ZONAS[i]} ---")
        print(f"  Modo               : {'MANUAL' if z['modo_manual'].read_value() else 'AUTOMATICO'}")
        print(f"  Humedad actual     : {z['humedad'].read_value():.0f} %")
        print(f"  Caudal instantaneo : {z['caudal'].read_value():.0f} L/min")
        print(f"  Umbral minimo      : {z['umbral_min'].read_value():.0f} %")
        print(f"  Umbral maximo      : {z['umbral_max'].read_value():.0f} %")
        print(f"  Valvula            : {'ABIERTA' if z['valvula'].read_value() else 'CERRADA'}")
        print(f"  Alarma humedad baja       : {z['alarma_baja'].read_value()}")
        print(f"  Alarma encharcamiento     : {z['alarma_encharcamiento'].read_value()}")


def main() -> None:
    print(f"Conectando al servidor OPC UA en {SERVER_URL} ...")
    with Client(url=SERVER_URL) as client:
        idx = client.get_namespace_index(NAMESPACE_URI)
        objects = client.get_objects_node()
        zonas = [obtener_nodos_zona(objects, idx, nombre) for nombre in NOMBRES_NODOS]
        print("Conectado.")

        while True:
            opcion = input(MENU.format(url=SERVER_URL)).strip()

            if opcion == "1":
                mostrar_estado(zonas)
            elif opcion == "2":
                zi = pedir_zona()
                if zi is None:
                    continue
                nuevo = pedir_numero("  nuevo umbral minimo (%): ")
                if nuevo is not None:
                    zonas[zi]["umbral_min"].write_value(float(nuevo))
                    print(f"  [OK] umbral minimo de {NOMBRES_ZONAS[zi]} escrito con {nuevo}")
            elif opcion == "3":
                zi = pedir_zona()
                if zi is None:
                    continue
                nuevo = pedir_numero("  nuevo umbral maximo (%): ")
                if nuevo is not None:
                    zonas[zi]["umbral_max"].write_value(float(nuevo))
                    print(f"  [OK] umbral maximo de {NOMBRES_ZONAS[zi]} escrito con {nuevo}")
            elif opcion == "4":
                zi = pedir_zona()
                if zi is None:
                    continue
                zonas[zi]["modo_manual"].write_value(True)
                zonas[zi]["valvula"].write_value(True)
                print(f"  [OK] valvula de {NOMBRES_ZONAS[zi]} forzada a ABIERTA (modo MANUAL)")
            elif opcion == "5":
                zi = pedir_zona()
                if zi is None:
                    continue
                zonas[zi]["modo_manual"].write_value(True)
                zonas[zi]["valvula"].write_value(False)
                print(f"  [OK] valvula de {NOMBRES_ZONAS[zi]} forzada a CERRADA (modo MANUAL)")
            elif opcion == "6":
                zi = pedir_zona()
                if zi is None:
                    continue
                zonas[zi]["modo_manual"].write_value(False)
                print(f"  [OK] {NOMBRES_ZONAS[zi]} devuelta a modo AUTOMATICO (la controla el SCADA)")
            elif opcion == "0":
                break
            else:
                print("  [!] opcion invalida")


if __name__ == "__main__":
    main()
