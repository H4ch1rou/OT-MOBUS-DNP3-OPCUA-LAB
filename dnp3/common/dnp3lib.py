"""
Codec DNP3 minimo, hecho a mano para este laboratorio.

No existe una libreria DNP3 pura en Python que sea liviana y mantenida
(la unica completa, `pydnp3`, envuelve la libreria C++ `opendnp3` y
requiere compilarla con cmake/g++ dentro de la imagen Docker, algo fragil
y lento para un laboratorio). Por eso este modulo implementa, a mano, el
subconjunto de IEEE 1815 (DNP3) que este laboratorio necesita:

  - Capa de enlace (Data Link Layer) real, con CRC-16/DNP verificado
    contra el vector de prueba estandar ("123456789" -> 0xEA82).
  - Capa de transporte (Transport Layer) de un solo segmento (FIR=FIN=1).
  - Capa de aplicacion (Application Layer) con los function codes y
    grupos de objetos necesarios para exponer sensores/alarmas y
    controlar valvulas/umbrales de una central de riego:

      Function codes: CONFIRM (0x00), READ (0x01), DIRECT_OPERATE (0x05),
      RESPONSE (0x81), UNSOLICITED_RESPONSE (0x82).

      Grupos de objetos:
        Group  1 Var 2 - Binary Input (con flags)       -> alarmas
        Group 10 Var 2 - Binary Output Status (flags)   -> estado valvula/modo
        Group 12 Var 1 - CROB (Control Relay Output Blk)-> comando valvula/modo
        Group 30 Var 5 - Analog Input (float32 + flag)  -> humedad, caudal
        Group 40 Var 2 - Analog Output Status (16-bit)  -> estado umbrales
        Group 41 Var 2 - Analog Output command (16-bit) -> comando umbrales
        Group 60 Var 1 - Class 0 Data (usado solo como header de integrity poll)

Simplificaciones deliberadas frente al estandar completo (documentadas
tambien en PROTOCOLO-DNP3.md):
  - Sin "capa de enlace confirmada" (siempre Unconfirmed User Data).
  - Sin fragmentacion multi-frame (todos nuestros mensajes caben en un
    solo segmento de transporte).
  - Las respuestas no solicitadas reenvian el valor ESTATICO del punto
    que cambio (Binary Input Var 2), en vez de un objeto de EVENTO con
    marca de tiempo (Group 2/32, etc.) como haria una implementacion
    completa. El punto pedagogico central -- que el outstation puede
    iniciar la comunicacion sin que el master pregunte primero -- se
    mantiene intacto.
  - Sin autenticacion Secure Authentication (SAv5/SAv6): DNP3 "clasico"
    tampoco la tiene por defecto, asi que esto refleja fielmente la
    inseguridad real del protocolo, no es una simplificacion que oculte
    algo.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field

# --------------------------------------------------------------------------
# CRC-16/DNP (poly 0x3D65, reflejado 0xA6BC; init 0x0000; xorout 0xFFFF)
# Verificado contra el vector de prueba estandar: crc16_dnp(b"123456789") == 0xEA82
# --------------------------------------------------------------------------

_POLY_REFLECTED = 0xA6BC


def crc16_dnp(data: bytes) -> int:
    crc = 0x0000
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ _POLY_REFLECTED
            else:
                crc >>= 1
    return (~crc) & 0xFFFF


# --------------------------------------------------------------------------
# Capa de enlace (Data Link Layer)
# --------------------------------------------------------------------------

START1, START2 = 0x05, 0x64

# Control byte para "Unconfirmed User Data" (function code de enlace = 4).
# DIR=1 para tramas enviadas por el master, DIR=0 para las del outstation.
# Son los valores 0xC4 / 0x44 que se ven tal cual en capturas DNP3 reales.
LINK_CTRL_FROM_MASTER = 0xC4
LINK_CTRL_FROM_OUTSTATION = 0x44

_MAX_BLOCK = 16


def build_link_frame(dest: int, src: int, control: int, user_data: bytes) -> bytes:
    """Arma UNA trama de enlace completa (header + bloques de datos con
    su propio CRC cada uno, tal como especifica IEEE 1815)."""
    if len(user_data) > 250:
        raise ValueError("user_data excede el maximo de 250 bytes de una trama de enlace")

    length = 5 + len(user_data)  # control(1) + dest(2) + src(2) + user_data
    header = bytes([START1, START2, length, control]) + struct.pack("<HH", dest, src)
    frame = header + struct.pack("<H", crc16_dnp(header))

    for i in range(0, len(user_data), _MAX_BLOCK):
        block = user_data[i : i + _MAX_BLOCK]
        frame += block + struct.pack("<H", crc16_dnp(block))

    return frame


@dataclass
class LinkFrame:
    dest: int
    src: int
    control: int
    user_data: bytes
    consumed: int


def parse_link_frame(buf: bytes) -> LinkFrame | None:
    """Extrae UNA trama de enlace desde el inicio de `buf`.

    Devuelve None si no hay suficientes bytes todavia (el llamador debe
    seguir leyendo del socket). Lanza ValueError si los bytes presentes
    no son una trama DNP3 valida (start bytes o CRC incorrectos).
    """
    if len(buf) < 10:
        return None
    if buf[0] != START1 or buf[1] != START2:
        raise ValueError(f"start bytes invalidos: {buf[0]:#x} {buf[1]:#x}")

    length = buf[2]
    control = buf[3]
    dest, src = struct.unpack("<HH", buf[4:8])

    header = bytes(buf[0:8])
    header_crc = struct.unpack("<H", buf[8:10])[0]
    if crc16_dnp(header) != header_crc:
        raise ValueError("CRC de header invalido")

    user_len = length - 5
    pos = 10
    user_data = bytearray()
    remaining = user_len

    while remaining > 0:
        chunk = min(_MAX_BLOCK, remaining)
        if len(buf) < pos + chunk + 2:
            return None  # trama incompleta, falta leer mas del socket
        block = bytes(buf[pos : pos + chunk])
        pos += chunk
        block_crc = struct.unpack("<H", buf[pos : pos + 2])[0]
        pos += 2
        if crc16_dnp(block) != block_crc:
            raise ValueError("CRC de bloque invalido")
        user_data += block
        remaining -= chunk

    return LinkFrame(dest=dest, src=src, control=control, user_data=bytes(user_data), consumed=pos)


# --------------------------------------------------------------------------
# Capa de transporte (Transport Layer) -- un solo segmento por mensaje
# --------------------------------------------------------------------------


def build_transport_segment(payload: bytes, seq: int, fir: bool = True, fin: bool = True) -> bytes:
    hdr = (0x80 if fin else 0) | (0x40 if fir else 0) | (seq & 0x3F)
    return bytes([hdr]) + payload


def parse_transport_segment(buf: bytes):
    hdr = buf[0]
    fir = bool(hdr & 0x40)
    fin = bool(hdr & 0x80)
    seq = hdr & 0x3F
    return fir, fin, seq, buf[1:]


# --------------------------------------------------------------------------
# Capa de aplicacion (Application Layer)
# --------------------------------------------------------------------------

FC_CONFIRM = 0x00
FC_READ = 0x01
FC_WRITE = 0x02
FC_DIRECT_OPERATE = 0x05
FC_RESPONSE = 0x81
FC_UNSOLICITED_RESPONSE = 0x82

FUNC_NAMES = {
    FC_CONFIRM: "CONFIRM",
    FC_READ: "READ",
    FC_WRITE: "WRITE",
    FC_DIRECT_OPERATE: "DIRECT_OPERATE",
    FC_RESPONSE: "RESPONSE",
    FC_UNSOLICITED_RESPONSE: "UNSOLICITED_RESPONSE",
}


def build_app_control(fir: bool = True, fin: bool = True, con: bool = False, uns: bool = False, seq: int = 0) -> int:
    b = 0
    if fir:
        b |= 0x80
    if fin:
        b |= 0x40
    if con:
        b |= 0x20
    if uns:
        b |= 0x10
    b |= seq & 0x0F
    return b


@dataclass
class AppControl:
    fir: bool
    fin: bool
    con: bool
    uns: bool
    seq: int


def parse_app_control(b: int) -> AppControl:
    return AppControl(
        fir=bool(b & 0x80),
        fin=bool(b & 0x40),
        con=bool(b & 0x20),
        uns=bool(b & 0x10),
        seq=b & 0x0F,
    )


# ---- Object headers / qualifiers ----
# 0x06 = sin rango, "todos los objetos" (usado en el pedido de integrity poll)
# 0x00 = rango de 8 bits (start, stop) -- usado en respuestas de datos estaticos
# 0x17 = 8-bit count + 8-bit index por objeto -- usado en comandos (CROB / AO)

QUAL_ALL = 0x06
QUAL_RANGE_8BIT = 0x00
QUAL_COUNT_INDEX_8BIT = 0x17

GROUP_BINARY_INPUT = 1
VAR_BINARY_INPUT_FLAGS = 2
GROUP_BINARY_OUTPUT_STATUS = 10
VAR_BINARY_OUTPUT_STATUS_FLAGS = 2
GROUP_CROB = 12
VAR_CROB = 1
GROUP_ANALOG_INPUT = 30
VAR_ANALOG_INPUT_FLOAT = 5
GROUP_ANALOG_OUTPUT_STATUS = 40
VAR_ANALOG_OUTPUT_STATUS_16 = 2
GROUP_ANALOG_OUTPUT_COMMAND = 41
VAR_ANALOG_OUTPUT_COMMAND_16 = 2
GROUP_CLASS_DATA = 60
VAR_CLASS_0 = 1

CROB_OP_LATCH_ON = 3
CROB_OP_LATCH_OFF = 4
CROB_STATUS_SUCCESS = 0


def obj_header_class0_poll() -> bytes:
    """Object header estandar para un integrity poll (pedir Class 0 completa)."""
    return bytes([GROUP_CLASS_DATA, VAR_CLASS_0, QUAL_ALL])


def obj_header_range(group: int, var: int, start: int, stop: int) -> bytes:
    return bytes([group, var, QUAL_RANGE_8BIT, start, stop])


def obj_header_count_prefix(group: int, var: int, count: int = 1) -> bytes:
    return bytes([group, var, QUAL_COUNT_INDEX_8BIT, count])


# ---- Encoders/decoders de puntos ----


def encode_binary_flag(value: bool, online: bool = True) -> bytes:
    flag = (0x01 if online else 0x00) | (0x80 if value else 0x00)
    return bytes([flag])


def decode_binary_flag(b: int) -> bool:
    return bool(b & 0x80)


def encode_analog_float(value: float, online: bool = True) -> bytes:
    flag = 0x01 if online else 0x00
    return bytes([flag]) + struct.pack("<f", value)


def decode_analog_float(buf: bytes) -> float:
    return struct.unpack("<f", buf[1:5])[0]


def encode_ao_status16(value: int, online: bool = True) -> bytes:
    flag = 0x01 if online else 0x00
    return bytes([flag]) + struct.pack("<h", value)


def decode_ao_status16(buf: bytes) -> int:
    return struct.unpack("<h", buf[1:3])[0]


def encode_crob(op_type: int, count: int = 1, on_time: int = 0, off_time: int = 0, status: int = 0) -> bytes:
    control_code = op_type & 0x0F
    return struct.pack("<BBIIB", control_code, count, on_time, off_time, status)


@dataclass
class Crob:
    op_type: int
    count: int
    on_time: int
    off_time: int
    status: int


def decode_crob(buf: bytes) -> Crob:
    control_code, count, on_time, off_time, status = struct.unpack("<BBIIB", buf[:11])
    return Crob(op_type=control_code & 0x0F, count=count, on_time=on_time, off_time=off_time, status=status)


def encode_ao_command16(value: int, status: int = 0) -> bytes:
    return struct.pack("<hB", value, status)


def decode_ao_command16(buf: bytes):
    value, status = struct.unpack("<hB", buf[:3])
    return value, status


# --------------------------------------------------------------------------
# Ensamblado de mensajes de aplicacion completos (header + objetos)
# --------------------------------------------------------------------------


def build_app_message(function: int, seq: int, objects: bytes = b"", con: bool = False, uns: bool = False, iin: int = 0x0000) -> bytes:
    """Arma el payload de capa de aplicacion completo.

    Para requests (READ, DIRECT_OPERATE, CONFIRM) no hay IIN.
    Para responses (RESPONSE, UNSOLICITED_RESPONSE) SI llevan 2 bytes de IIN.
    """
    ctrl = build_app_control(fir=True, fin=True, con=con, uns=uns, seq=seq)
    msg = bytes([ctrl, function])
    if function in (FC_RESPONSE, FC_UNSOLICITED_RESPONSE):
        msg += struct.pack("<H", iin)
    msg += objects
    return msg


@dataclass
class AppMessage:
    control: AppControl
    function: int
    iin: int
    objects: bytes


def parse_app_message(buf: bytes) -> AppMessage:
    ctrl = parse_app_control(buf[0])
    function = buf[1]
    offset = 2
    iin = 0
    if function in (FC_RESPONSE, FC_UNSOLICITED_RESPONSE):
        iin = struct.unpack("<H", buf[2:4])[0]
        offset = 4
    return AppMessage(control=ctrl, function=function, iin=iin, objects=buf[offset:])


# --------------------------------------------------------------------------
# Envoltura de una capa de aplicacion completa en enlace+transporte, lista
# para enviar por el socket TCP (puerto estandar DNP3: 20000)
# --------------------------------------------------------------------------

DEFAULT_PORT = 20000


def wrap_for_wire(dest: int, src: int, from_master: bool, app_payload: bytes, transport_seq: int = 0) -> bytes:
    control = LINK_CTRL_FROM_MASTER if from_master else LINK_CTRL_FROM_OUTSTATION
    transport_payload = build_transport_segment(app_payload, seq=transport_seq)
    return build_link_frame(dest=dest, src=src, control=control, user_data=transport_payload)


def unwrap_from_wire(buf: bytes) -> tuple[AppMessage, int] | None:
    """A partir de bytes crudos leidos del socket, intenta extraer UN
    mensaje de aplicacion completo. Devuelve (AppMessage, bytes_consumidos)
    o None si aun faltan bytes por leer."""
    link = parse_link_frame(buf)
    if link is None:
        return None
    _fir, _fin, _seq, app_payload = parse_transport_segment(link.user_data)
    return parse_app_message(app_payload), link.consumed
