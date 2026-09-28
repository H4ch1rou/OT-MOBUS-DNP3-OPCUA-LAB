"""
Herramienta de operador manual para la Central de Riego DNP3 (multi-zona).

Se conecta DIRECTO como cliente DNP3 al outstation (`dnp3-outstation`),
sin pasar por la Central SCADA (`dnp3-master`). Es exactamente el mismo
punto de discusion que en el laboratorio Modbus: el outstation acepta la
conexion sin verificar si "de verdad" eres el SCADA autorizado.

Usa sockets sincronos (no asyncio) porque es una consola interactiva:
cada opcion del menu manda un mensaje y espera su respuesta antes de
seguir, no hay nada corriendo "en el fondo" mientras el operador piensa
que opcion elegir.

Uso:
    docker compose run --rm operador
"""

import os
import socket

import dnp3lib as d

OUTSTATION_HOST = os.environ.get("OUTSTATION_HOST", "dnp3-outstation")
OUTSTATION_PORT = int(os.environ.get("OUTSTATION_PORT", str(d.DEFAULT_PORT)))
MASTER_ADDR = int(os.environ.get("MASTER_ADDR", "1"))
OUTSTATION_ADDR = int(os.environ.get("OUTSTATION_ADDR", "10"))

NOMBRES_ZONAS = [
    "Zona 1 - Parronal",
    "Zona 2 - Hortalizas",
    "Zona 3 - Frutales",
    "Zona 4 - Vivero",
]
N_ZONAS = len(NOMBRES_ZONAS)

MENU = """
=== Operador manual DNP3 - Central de Riego (outstation: {host}:{port}) ===
1) Ver estado de todas las zonas (integrity poll)
2) Cambiar umbral MINIMO de humedad de una zona
3) Cambiar umbral MAXIMO de humedad de una zona
4) Forzar APERTURA manual de la valvula de una zona (pasa a modo MANUAL)
5) Forzar CIERRE manual de la valvula de una zona (pasa a modo MANUAL)
6) Devolver una zona a modo AUTOMATICO (la controla el SCADA)
0) Salir
> """

_seq = 0
_transport_seq = 0


def siguiente_seq() -> int:
    global _seq
    s = _seq
    _seq = (_seq + 1) % 16
    return s


def siguiente_transport_seq() -> int:
    global _transport_seq
    s = _transport_seq
    _transport_seq = (_transport_seq + 1) % 64
    return s


def enviar_y_recibir(sock: socket.socket, app_payload: bytes) -> d.AppMessage:
    """Manda un mensaje y espera su RESPONSE. Si mientras tanto llega una
    UNSOLICITED_RESPONSE espontanea (el outstation puede mandarla en
    cualquier momento, sin relacion con lo que pedimos), la confirma y
    sigue esperando la respuesta que realmente nos interesa -- si no, la
    proxima llamada la confundiria con la respuesta a OTRO pedido."""
    wire = d.wrap_for_wire(
        dest=OUTSTATION_ADDR, src=MASTER_ADDR, from_master=True,
        app_payload=app_payload, transport_seq=siguiente_transport_seq(),
    )
    sock.sendall(wire)

    buffer = bytearray()
    while True:
        resultado = d.unwrap_from_wire(bytes(buffer))
        if resultado is None:
            buffer += sock.recv(4096)
            continue

        msg, consumidos = resultado
        del buffer[:consumidos]

        if msg.function == d.FC_UNSOLICITED_RESPONSE:
            print(f"  [info] llego una UNSOLICITED_RESPONSE (seq={msg.control.seq}) mientras esperabas tu respuesta; se confirma y se sigue esperando")
            confirm = d.build_app_message(d.FC_CONFIRM, seq=msg.control.seq, uns=True)
            confirm_wire = d.wrap_for_wire(
                dest=OUTSTATION_ADDR, src=MASTER_ADDR, from_master=True,
                app_payload=confirm, transport_seq=siguiente_transport_seq(),
            )
            sock.sendall(confirm_wire)
            continue

        return msg


def leer_estado(sock: socket.socket):
    seq = siguiente_seq()
    app = d.build_app_message(d.FC_READ, seq=seq, objects=d.obj_header_class0_poll())
    msg = enviar_y_recibir(sock, app)

    zonas = [
        {"humedad": 0.0, "caudal": 0.0, "umbral_min": 0, "umbral_max": 0, "valvula": False, "modo_manual": False,
         "alarma_baja": False, "alarma_encharcamiento": False}
        for _ in range(N_ZONAS)
    ]

    buf = msg.objects
    pos = 0
    while pos < len(buf):
        group, _var, _qual, start, stop = buf[pos], buf[pos + 1], buf[pos + 2], buf[pos + 3], buf[pos + 4]
        pos += 5
        n = stop - start + 1
        for i in range(n):
            zona, cual = divmod(start + i, 2)
            if group == d.GROUP_BINARY_INPUT:
                valor = d.decode_binary_flag(buf[pos]); pos += 1
                zonas[zona]["alarma_baja" if cual == 0 else "alarma_encharcamiento"] = valor
            elif group == d.GROUP_BINARY_OUTPUT_STATUS:
                valor = d.decode_binary_flag(buf[pos]); pos += 1
                zonas[zona]["valvula" if cual == 0 else "modo_manual"] = valor
            elif group == d.GROUP_ANALOG_INPUT:
                valor = d.decode_analog_float(buf[pos:pos + 5]); pos += 5
                zonas[zona]["humedad" if cual == 0 else "caudal"] = valor
            elif group == d.GROUP_ANALOG_OUTPUT_STATUS:
                valor = d.decode_ao_status16(buf[pos:pos + 3]); pos += 3
                zonas[zona]["umbral_min" if cual == 0 else "umbral_max"] = valor
    return zonas


def mostrar_estado(sock: socket.socket) -> None:
    zonas = leer_estado(sock)
    for i, z in enumerate(zonas):
        print(f"\n  --- {NOMBRES_ZONAS[i]} ---")
        print(f"  Modo               : {'MANUAL' if z['modo_manual'] else 'AUTOMATICO'}")
        print(f"  Humedad actual     : {z['humedad']:.0f} %")
        print(f"  Caudal instantaneo : {z['caudal']:.0f} L/min")
        print(f"  Umbral minimo      : {z['umbral_min']} %")
        print(f"  Umbral maximo      : {z['umbral_max']} %")
        print(f"  Valvula            : {'ABIERTA' if z['valvula'] else 'CERRADA'}")
        print(f"  Alarma humedad baja       : {z['alarma_baja']}")
        print(f"  Alarma encharcamiento     : {z['alarma_encharcamiento']}")


def operar_crob(sock: socket.socket, indice_punto: int, abrir: bool) -> None:
    seq = siguiente_seq()
    op = d.CROB_OP_LATCH_ON if abrir else d.CROB_OP_LATCH_OFF
    objs = d.obj_header_count_prefix(d.GROUP_CROB, d.VAR_CROB, count=1) + bytes([indice_punto]) + d.encode_crob(op)
    app = d.build_app_message(d.FC_DIRECT_OPERATE, seq=seq, objects=objs)
    enviar_y_recibir(sock, app)


def operar_analog_output(sock: socket.socket, indice_punto: int, valor: int) -> None:
    seq = siguiente_seq()
    objs = d.obj_header_count_prefix(d.GROUP_ANALOG_OUTPUT_COMMAND, d.VAR_ANALOG_OUTPUT_COMMAND_16, count=1) + \
        bytes([indice_punto]) + d.encode_ao_command16(valor)
    app = d.build_app_message(d.FC_DIRECT_OPERATE, seq=seq, objects=objs)
    enviar_y_recibir(sock, app)


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


def main() -> None:
    print(f"Conectando al outstation DNP3 en {OUTSTATION_HOST}:{OUTSTATION_PORT} ...")
    with socket.create_connection((OUTSTATION_HOST, OUTSTATION_PORT), timeout=10) as sock:
        sock.settimeout(10)
        print("Conectado.")

        while True:
            opcion = input(MENU.format(host=OUTSTATION_HOST, port=OUTSTATION_PORT)).strip()

            if opcion == "1":
                mostrar_estado(sock)
            elif opcion == "2":
                zona = pedir_zona()
                if zona is None:
                    continue
                nuevo = pedir_entero("  nuevo umbral minimo (%): ")
                if nuevo is not None:
                    operar_analog_output(sock, zona * 2, nuevo)
                    print(f"  [OK] umbral minimo de {NOMBRES_ZONAS[zona]} escrito con {nuevo}")
            elif opcion == "3":
                zona = pedir_zona()
                if zona is None:
                    continue
                nuevo = pedir_entero("  nuevo umbral maximo (%): ")
                if nuevo is not None:
                    operar_analog_output(sock, zona * 2 + 1, nuevo)
                    print(f"  [OK] umbral maximo de {NOMBRES_ZONAS[zona]} escrito con {nuevo}")
            elif opcion == "4":
                zona = pedir_zona()
                if zona is None:
                    continue
                operar_crob(sock, zona * 2 + 1, True)  # modo manual = True
                operar_crob(sock, zona * 2, True)      # valvula = abierta
                print(f"  [OK] valvula de {NOMBRES_ZONAS[zona]} forzada a ABIERTA (modo MANUAL)")
            elif opcion == "5":
                zona = pedir_zona()
                if zona is None:
                    continue
                operar_crob(sock, zona * 2 + 1, True)  # modo manual = True
                operar_crob(sock, zona * 2, False)     # valvula = cerrada
                print(f"  [OK] valvula de {NOMBRES_ZONAS[zona]} forzada a CERRADA (modo MANUAL)")
            elif opcion == "6":
                zona = pedir_zona()
                if zona is None:
                    continue
                operar_crob(sock, zona * 2 + 1, False)  # modo manual = False
                print(f"  [OK] {NOMBRES_ZONAS[zona]} devuelta a modo AUTOMATICO (la controla el SCADA)")
            elif opcion == "0":
                break
            else:
                print("  [!] opcion invalida")


if __name__ == "__main__":
    main()
