"""
DNP3 outstation (esclavo/RTU) de una Central de Riego con 4 zonas.

Mismo proceso fisico simulado que el laboratorio Modbus (para poder
comparar ambos protocolos sobre el mismo escenario), expuesto ahora via
DNP3 TCP (puerto 20000) usando el codec propio en `dnp3lib.py`:

  Analog Input  (Grupo 30 Var 5, float) -> humedad, caudal      (index = zona*2 + {0,1})
  Analog Output (Grupo 40/41, 16-bit)   -> umbral_min, umbral_max (index = zona*2 + {0,1})
  Binary Input  (Grupo 1 Var 2)         -> alarma_baja, alarma_encharcamiento (index = zona*2 + {0,1})
  Binary Output (Grupo 10/12)           -> valvula, modo_manual (index = zona*2 + {0,1})

A diferencia de Modbus (estrictamente iniciado por el master), este
outstation puede iniciar la comunicacion por su cuenta: cuando una alarma
cambia de estado, envia una UNSOLICITED_RESPONSE sin que nadie se lo
pida, y espera un CONFIRM del master.
"""

import asyncio
import logging
import os
import struct

import dnp3lib as d

logging.basicConfig(level=logging.INFO, format="%(asctime)s [RTU-RIEGO-DNP3] %(message)s")
log = logging.getLogger("dnp3-outstation")

HOST = "0.0.0.0"
PORT = int(os.environ.get("DNP3_PORT", str(d.DEFAULT_PORT)))
MASTER_ADDR = int(os.environ.get("MASTER_ADDR", "1"))
OUTSTATION_ADDR = int(os.environ.get("OUTSTATION_ADDR", "10"))

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
UMBRAL_MIN_DEFAULT = 30
UMBRAL_MAX_DEFAULT = 80

# Los indices 0 y 1, dentro de cada grupo de puntos, son "por zona":
#   indice = zona*2 + 0   ->  primera variable del grupo (humedad / umbral_min / alarma_baja / valvula)
#   indice = zona*2 + 1   ->  segunda variable del grupo  (caudal / umbral_max / encharcamiento / modo_manual)


class EstadoZonas:
    def __init__(self) -> None:
        self.humedad = [z["humedad_inicial"] for z in ZONAS]
        self.caudal = [0.0] * N_ZONAS
        self.umbral_min = [UMBRAL_MIN_DEFAULT] * N_ZONAS
        self.umbral_max = [UMBRAL_MAX_DEFAULT] * N_ZONAS
        self.valvula = [False] * N_ZONAS
        self.modo_manual = [False] * N_ZONAS
        self.alarma_baja = [False] * N_ZONAS
        self.alarma_encharcamiento = [False] * N_ZONAS

    # -- indices DNP3 --
    def idx_ai_humedad(self, z):
        return z * 2

    def idx_ai_caudal(self, z):
        return z * 2 + 1

    def idx_ao_umbral_min(self, z):
        return z * 2

    def idx_ao_umbral_max(self, z):
        return z * 2 + 1

    def idx_bi_alarma_baja(self, z):
        return z * 2

    def idx_bi_encharcamiento(self, z):
        return z * 2 + 1

    def idx_bo_valvula(self, z):
        return z * 2

    def idx_bo_modo_manual(self, z):
        return z * 2 + 1


estado = EstadoZonas()


def build_class0_response(seq: int) -> bytes:
    """Arma el payload de aplicacion de una RESPONSE con todos los puntos
    (integrity poll completo): Binary Input, Binary Output Status,
    Analog Input, Analog Output Status, en ese orden."""
    n = N_ZONAS * 2  # 2 puntos por zona en cada grupo

    bi_vals = [False] * n
    bo_vals = [False] * n
    ai_vals = [0.0] * n
    ao_vals = [0] * n

    for z in range(N_ZONAS):
        bi_vals[estado.idx_bi_alarma_baja(z)] = estado.alarma_baja[z]
        bi_vals[estado.idx_bi_encharcamiento(z)] = estado.alarma_encharcamiento[z]
        bo_vals[estado.idx_bo_valvula(z)] = estado.valvula[z]
        bo_vals[estado.idx_bo_modo_manual(z)] = estado.modo_manual[z]
        ai_vals[estado.idx_ai_humedad(z)] = estado.humedad[z]
        ai_vals[estado.idx_ai_caudal(z)] = estado.caudal[z]
        ao_vals[estado.idx_ao_umbral_min(z)] = estado.umbral_min[z]
        ao_vals[estado.idx_ao_umbral_max(z)] = estado.umbral_max[z]

    objs = b""
    objs += d.obj_header_range(d.GROUP_BINARY_INPUT, d.VAR_BINARY_INPUT_FLAGS, 0, n - 1)
    objs += b"".join(d.encode_binary_flag(v) for v in bi_vals)

    objs += d.obj_header_range(d.GROUP_BINARY_OUTPUT_STATUS, d.VAR_BINARY_OUTPUT_STATUS_FLAGS, 0, n - 1)
    objs += b"".join(d.encode_binary_flag(v) for v in bo_vals)

    objs += d.obj_header_range(d.GROUP_ANALOG_INPUT, d.VAR_ANALOG_INPUT_FLOAT, 0, n - 1)
    objs += b"".join(d.encode_analog_float(v) for v in ai_vals)

    objs += d.obj_header_range(d.GROUP_ANALOG_OUTPUT_STATUS, d.VAR_ANALOG_OUTPUT_STATUS_16, 0, n - 1)
    objs += b"".join(d.encode_ao_status16(v) for v in ao_vals)

    return d.build_app_message(d.FC_RESPONSE, seq=seq, objects=objs, iin=0x0000)


def parse_object_header(buf: bytes, pos: int):
    group, var, qual = buf[pos], buf[pos + 1], buf[pos + 2]
    return group, var, qual, pos + 3


def handle_direct_operate(objs: bytes) -> bytes:
    """Procesa un DIRECT_OPERATE (CROB o Analog Output Command) y devuelve
    el mismo object header con el resultado (status=SUCCESS) para la
    RESPONSE, tal como exige el estandar."""
    group, var, qual, pos = parse_object_header(objs, 0)
    assert qual == d.QUAL_COUNT_INDEX_8BIT, f"qualifier no soportado en DIRECT_OPERATE: {qual:#x}"
    count = objs[pos]
    pos += 1

    out = bytes([group, var, qual, count])

    for _ in range(count):
        index = objs[pos]
        pos += 1

        if group == d.GROUP_CROB:
            crob = d.decode_crob(objs[pos : pos + 11])
            pos += 11
            zona, cual = divmod(index, 2)
            valor = crob.op_type == d.CROB_OP_LATCH_ON
            if cual == 0:
                estado.valvula[zona] = valor
                log.info("DIRECT_OPERATE: valvula %s -> %s", ZONAS[zona]["nombre"], "ABIERTA" if valor else "CERRADA")
            else:
                estado.modo_manual[zona] = valor
                log.info("DIRECT_OPERATE: modo %s -> %s", ZONAS[zona]["nombre"], "MANUAL" if valor else "AUTOMATICO")
            out += bytes([index]) + d.encode_crob(crob.op_type, crob.count, crob.on_time, crob.off_time, d.CROB_STATUS_SUCCESS)

        elif group == d.GROUP_ANALOG_OUTPUT_COMMAND:
            valor, _status = d.decode_ao_command16(objs[pos : pos + 3])
            pos += 3
            zona, cual = divmod(index, 2)
            valor = max(0, min(100, valor))
            if cual == 0:
                estado.umbral_min[zona] = valor
                log.info("DIRECT_OPERATE: umbral minimo %s -> %d", ZONAS[zona]["nombre"], valor)
            else:
                estado.umbral_max[zona] = valor
                log.info("DIRECT_OPERATE: umbral maximo %s -> %d", ZONAS[zona]["nombre"], valor)
            out += bytes([index]) + d.encode_ao_command16(valor, 0)

        else:
            raise ValueError(f"grupo no soportado en DIRECT_OPERATE: {group}")

    return out


class GestorConexiones:
    """Un outstation DNP3 "de verdad" normalmente solo acepta UN master
    autorizado. Este laboratorio acepta varias conexiones simultaneas a
    proposito (como el esclavo Modbus del otro laboratorio) para poder
    mostrar el mismo problema de fondo: no hay ninguna autenticacion que
    distinga al SCADA legitimo (`dnp3-master`) de cualquier otro cliente
    (`webhmi`, `operador`, o un atacante) conectandose directamente al
    puerto 20000 y mandando comandos DIRECT_OPERATE como si fuera el
    master. Las respuestas no solicitadas se mandan a TODOS los clientes
    conectados en ese momento (asi el sniffer las ve sin importar por
    cual conexion entraron los demas comandos)."""

    def __init__(self) -> None:
        self.writers: set[asyncio.StreamWriter] = set()
        self.unsol_seq = 0
        self.transport_seq = 0

    def siguiente_transport_seq(self) -> int:
        seq = self.transport_seq
        self.transport_seq = (self.transport_seq + 1) % 64
        return seq

    async def enviar_a(self, writer: asyncio.StreamWriter, app_payload: bytes) -> None:
        wire = d.wrap_for_wire(
            dest=MASTER_ADDR, src=OUTSTATION_ADDR, from_master=False,
            app_payload=app_payload, transport_seq=self.siguiente_transport_seq(),
        )
        writer.write(wire)
        await writer.drain()

    async def enviar_unsolicited_a_todos(self, zona: int) -> None:
        if not self.writers:
            return

        n_idx0 = estado.idx_bi_alarma_baja(zona)
        n_idx1 = estado.idx_bi_encharcamiento(zona)
        objs = d.obj_header_range(d.GROUP_BINARY_INPUT, d.VAR_BINARY_INPUT_FLAGS, n_idx0, n_idx1)
        objs += d.encode_binary_flag(estado.alarma_baja[zona]) + d.encode_binary_flag(estado.alarma_encharcamiento[zona])

        seq = self.unsol_seq
        self.unsol_seq = (self.unsol_seq + 1) % 16
        app = d.build_app_message(d.FC_UNSOLICITED_RESPONSE, seq=seq, objects=objs, con=True, uns=True, iin=0x0000)
        log.info(
            "-> UNSOLICITED_RESPONSE seq=%d a %d cliente(s) (%s: alarma_baja=%s encharcamiento=%s) [nadie lo pidio]",
            seq, len(self.writers), ZONAS[zona]["nombre"], estado.alarma_baja[zona], estado.alarma_encharcamiento[zona],
        )
        for writer in list(self.writers):
            try:
                await self.enviar_a(writer, app)
            except (ConnectionError, OSError):
                pass


gestor = GestorConexiones()


async def manejar_mensaje(msg: d.AppMessage) -> bytes | None:
    if msg.function == d.FC_READ:
        return build_class0_response(seq=msg.control.seq)

    if msg.function == d.FC_DIRECT_OPERATE:
        eco = handle_direct_operate(msg.objects)
        return d.build_app_message(d.FC_RESPONSE, seq=msg.control.seq, objects=eco, iin=0x0000)

    if msg.function == d.FC_CONFIRM:
        log.info("<- CONFIRM recibido (seq=%d) para la ultima UNSOLICITED_RESPONSE", msg.control.seq)
        return None

    log.warning("function code no soportado: %#x", msg.function)
    return None


async def manejar_conexion(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    peer = writer.get_extra_info("peername")
    log.info("Cliente conectado desde %s (total conectados: %d)", peer, len(gestor.writers) + 1)
    gestor.writers.add(writer)
    buffer = bytearray()

    try:
        while True:
            datos = await reader.read(4096)
            if not datos:
                break
            buffer += datos

            while True:
                try:
                    resultado = d.unwrap_from_wire(bytes(buffer))
                except ValueError as exc:
                    log.error("trama DNP3 invalida de %s, descartando buffer: %s", peer, exc)
                    buffer.clear()
                    break

                if resultado is None:
                    break

                msg, consumidos = resultado
                del buffer[:consumidos]

                nombre_fc = d.FUNC_NAMES.get(msg.function, hex(msg.function))
                log.info("<- %s (seq=%d) de %s", nombre_fc, msg.control.seq, peer)

                respuesta = await manejar_mensaje(msg)
                if respuesta is not None:
                    await gestor.enviar_a(writer, respuesta)
    except (ConnectionResetError, BrokenPipeError):
        pass
    finally:
        log.info("Cliente desconectado: %s", peer)
        gestor.writers.discard(writer)
        writer.close()


async def simular_proceso() -> None:
    alarma_baja_prev = list(estado.alarma_baja)
    alarma_ench_prev = list(estado.alarma_encharcamiento)

    while True:
        for z in range(N_ZONAS):
            if estado.valvula[z]:
                estado.humedad[z] += RIEGO_RATE
            estado.humedad[z] -= EVAPO_RATE
            estado.humedad[z] = max(0.0, min(100.0, estado.humedad[z]))
            estado.caudal[z] = RIEGO_RATE * 10 if estado.valvula[z] else 0.0

            estado.alarma_baja[z] = estado.humedad[z] < 10
            estado.alarma_encharcamiento[z] = estado.humedad[z] > 95

            estado_txt = "ABIERTA" if estado.valvula[z] else "CERRADA"
            log.info(
                "[%s] humedad=%5.1f%% valvula=%-7s caudal=%3.0f L/min alarma_baja=%s encharcamiento=%s",
                ZONAS[z]["nombre"], estado.humedad[z], estado_txt, estado.caudal[z],
                estado.alarma_baja[z], estado.alarma_encharcamiento[z],
            )

            if estado.alarma_baja[z] != alarma_baja_prev[z] or estado.alarma_encharcamiento[z] != alarma_ench_prev[z]:
                await gestor.enviar_unsolicited_a_todos(z)
                alarma_baja_prev[z] = estado.alarma_baja[z]
                alarma_ench_prev[z] = estado.alarma_encharcamiento[z]

        await asyncio.sleep(TICK_SECONDS)


async def main() -> None:
    server = await asyncio.start_server(manejar_conexion, HOST, PORT)
    log.info("Outstation DNP3 escuchando en %s:%d (direccion=%d, %d zonas)", HOST, PORT, OUTSTATION_ADDR, N_ZONAS)
    asyncio.create_task(simular_proceso())
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
