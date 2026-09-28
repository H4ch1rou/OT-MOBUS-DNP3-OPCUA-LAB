"""
Herramienta de operador/HMI manual para la Central de Riego (multi-zona).

Se conecta como cliente Modbus TCP directamente al RTU (modbus-slave) y
permite leer el estado y forzar escrituras (umbrales, valvulas, modo) a
mano, zona por zona.

Cada zona tiene una coil de "modo manual". Forzar apertura/cierre desde
aqui activa ese modo automaticamente, para que el cambio no sea
sobreescrito por el SCADA (`modbus-master`) en su siguiente ciclo de
control; la opcion 6 devuelve la zona a modo automatico.

Cada accion que ejecutas aqui genera una transaccion Modbus real en la
red `ot_network`: es el punto de partida ideal para observar el trafico
con el contenedor `sniffer` (tcpdump) mientras cambias valores.

Uso:
    docker compose run --rm operador
"""

import os

from pymodbus.client import ModbusTcpClient

SLAVE_HOST = os.environ.get("SLAVE_HOST", "modbus-slave")
SLAVE_PORT = int(os.environ.get("SLAVE_PORT", "502"))
UNIT_ID = int(os.environ.get("UNIT_ID", "1"))

NOMBRES_ZONAS = [
    "Zona 1 - Parronal",
    "Zona 2 - Hortalizas",
    "Zona 3 - Frutales",
    "Zona 4 - Vivero",
]
N_ZONAS = len(NOMBRES_ZONAS)
HR_STRIDE = 10
DI_STRIDE = 2

MENU = """
=== Operador manual - Central de Riego (RTU: {host}:{port}) ===
1) Ver estado de todas las zonas
2) Cambiar umbral MINIMO de humedad de una zona
3) Cambiar umbral MAXIMO de humedad de una zona
4) Forzar APERTURA manual de la valvula de una zona (pasa a modo MANUAL)
5) Forzar CIERRE manual de la valvula de una zona (pasa a modo MANUAL)
6) Devolver una zona a modo AUTOMATICO (la controla el SCADA)
0) Salir
> """


def hr_base(zona: int) -> int:
    return zona * HR_STRIDE


def co_valvula(zona: int) -> int:
    return zona


def co_modo_manual(zona: int) -> int:
    return N_ZONAS + zona


def di_base(zona: int) -> int:
    return zona * DI_STRIDE


def pedir_zona() -> int | None:
    for i, nombre in enumerate(NOMBRES_ZONAS, start=1):
        print(f"  {i}) {nombre}")
    valor = input(f"  zona (1-{N_ZONAS}): ").strip()
    if not valor.isdigit() or not (1 <= int(valor) <= N_ZONAS):
        print("  [!] zona invalida")
        return None
    return int(valor) - 1


def pedir_entero(mensaje: str) -> int | None:
    valor = input(mensaje).strip()
    if not valor.isdigit():
        print("  [!] valor invalido, debe ser un numero entero")
        return None
    return int(valor)


def mostrar_estado(client: ModbusTcpClient) -> None:
    for zona in range(N_ZONAS):
        datos = client.read_holding_registers(hr_base(zona), count=4, slave=UNIT_ID)
        valvula = client.read_coils(co_valvula(zona), count=1, slave=UNIT_ID)
        modo = client.read_coils(co_modo_manual(zona), count=1, slave=UNIT_ID)
        alarmas = client.read_discrete_inputs(di_base(zona), count=2, slave=UNIT_ID)

        if any(r.isError() for r in (datos, valvula, modo, alarmas)):
            print(f"  [!] error leyendo {NOMBRES_ZONAS[zona]}")
            continue

        humedad, caudal, umbral_min, umbral_max = datos.registers
        print(f"\n  --- {NOMBRES_ZONAS[zona]} ---")
        print(f"  Modo               : {'MANUAL' if modo.bits[0] else 'AUTOMATICO'}")
        print(f"  Humedad actual     : {humedad} %")
        print(f"  Caudal instantaneo : {caudal} L/min")
        print(f"  Umbral minimo      : {umbral_min} %")
        print(f"  Umbral maximo      : {umbral_max} %")
        print(f"  Valvula            : {'ABIERTA' if valvula.bits[0] else 'CERRADA'}")
        print(f"  Alarma humedad baja       : {alarmas.bits[0]}")
        print(f"  Alarma encharcamiento     : {alarmas.bits[1]}")


def main() -> None:
    client = ModbusTcpClient(SLAVE_HOST, port=SLAVE_PORT)
    if not client.connect():
        print(f"No se pudo conectar al RTU en {SLAVE_HOST}:{SLAVE_PORT}")
        return

    print(f"Conectado al RTU de riego en {SLAVE_HOST}:{SLAVE_PORT}")

    try:
        while True:
            opcion = input(MENU.format(host=SLAVE_HOST, port=SLAVE_PORT)).strip()

            if opcion == "1":
                mostrar_estado(client)
            elif opcion == "2":
                zona = pedir_zona()
                if zona is None:
                    continue
                nuevo = pedir_entero("  nuevo umbral minimo (%): ")
                if nuevo is not None:
                    client.write_register(hr_base(zona) + 2, nuevo, slave=UNIT_ID)
                    print(f"  [OK] umbral minimo de {NOMBRES_ZONAS[zona]} escrito con {nuevo}")
            elif opcion == "3":
                zona = pedir_zona()
                if zona is None:
                    continue
                nuevo = pedir_entero("  nuevo umbral maximo (%): ")
                if nuevo is not None:
                    client.write_register(hr_base(zona) + 3, nuevo, slave=UNIT_ID)
                    print(f"  [OK] umbral maximo de {NOMBRES_ZONAS[zona]} escrito con {nuevo}")
            elif opcion == "4":
                zona = pedir_zona()
                if zona is None:
                    continue
                client.write_coil(co_modo_manual(zona), True, slave=UNIT_ID)
                client.write_coil(co_valvula(zona), True, slave=UNIT_ID)
                print(f"  [OK] valvula de {NOMBRES_ZONAS[zona]} forzada a ABIERTA (modo MANUAL)")
            elif opcion == "5":
                zona = pedir_zona()
                if zona is None:
                    continue
                client.write_coil(co_modo_manual(zona), True, slave=UNIT_ID)
                client.write_coil(co_valvula(zona), False, slave=UNIT_ID)
                print(f"  [OK] valvula de {NOMBRES_ZONAS[zona]} forzada a CERRADA (modo MANUAL)")
            elif opcion == "6":
                zona = pedir_zona()
                if zona is None:
                    continue
                client.write_coil(co_modo_manual(zona), False, slave=UNIT_ID)
                print(f"  [OK] {NOMBRES_ZONAS[zona]} devuelta a modo AUTOMATICO (la controla el SCADA)")
            elif opcion == "0":
                break
            else:
                print("  [!] opcion invalida")
    finally:
        client.close()


if __name__ == "__main__":
    main()
