"""
DNP3 master (Central SCADA) de la Central de Riego.

A diferencia del master Modbus (que hace todo su trabajo con
lectura+escritura sincronas), este master mantiene UNA conexion TCP
persistente con el outstation y corre dos tareas concurrentes sobre ella:

  - `bucle_control()`: hace un integrity poll (READ, Class 0) cada
    `POLL_SECONDS`, aplica la misma logica de histeresis del laboratorio
    Modbus, y opera la valvula (DIRECT_OPERATE / CROB) cuando corresponde.
  - `receptor()`: lee continuamente el socket; si llega una RESPONSE la
    entrega a quien este esperando (el bucle de control), y si llega una
    UNSOLICITED_RESPONSE -- que el outstation puede mandar en cualquier
    momento, sin que nadie se lo pida -- la procesa de inmediato y
    responde con un CONFIRM.
"""

import asyncio
import logging
import os

import dnp3lib as d

logging.basicConfig(level=logging.INFO, format="%(asctime)s [SCADA-RIEGO-DNP3] %(message)s")
log = logging.getLogger("dnp3-master")

OUTSTATION_HOST = os.environ.get("OUTSTATION_HOST", "dnp3-outstation")
OUTSTATION_PORT = int(os.environ.get("OUTSTATION_PORT", str(d.DEFAULT_PORT)))
MASTER_ADDR = int(os.environ.get("MASTER_ADDR", "1"))
OUTSTATION_ADDR = int(os.environ.get("OUTSTATION_ADDR", "10"))
POLL_SECONDS = float(os.environ.get("POLL_SECONDS", "2"))

NOMBRES_ZONAS = [
    "Zona 1 - Parronal",
    "Zona 2 - Hortalizas",
    "Zona 3 - Frutales",
    "Zona 4 - Vivero",
]
N_ZONAS = len(NOMBRES_ZONAS)


class Snapshot:
    def __init__(self) -> None:
        self.humedad = [0.0] * N_ZONAS
        self.caudal = [0.0] * N_ZONAS
        self.umbral_min = [30] * N_ZONAS
        self.umbral_max = [80] * N_ZONAS
        self.valvula = [False] * N_ZONAS
        self.modo_manual = [False] * N_ZONAS
        self.alarma_baja = [False] * N_ZONAS
        self.alarma_encharcamiento = [False] * N_ZONAS


class MasterDNP3:
    def __init__(self) -> None:
        self.reader: asyncio.StreamReader | None = None
        self.writer: asyncio.StreamWriter | None = None
        self.req_seq = 0
        self.transport_seq = 0
        self.response_queue: asyncio.Queue[d.AppMessage] = asyncio.Queue()
        self.snapshot = Snapshot()

    def siguiente_seq(self) -> int:
        seq = self.req_seq
        self.req_seq = (self.req_seq + 1) % 16
        return seq

    def siguiente_transport_seq(self) -> int:
        seq = self.transport_seq
        self.transport_seq = (self.transport_seq + 1) % 64
        return seq

    async def conectar_con_reintento(self) -> None:
        while True:
            try:
                self.reader, self.writer = await asyncio.open_connection(OUTSTATION_HOST, OUTSTATION_PORT)
                log.info("conectado al outstation DNP3 en %s:%d", OUTSTATION_HOST, OUTSTATION_PORT)
                return
            except OSError:
                log.warning("no se pudo conectar al outstation, reintentando en 3s...")
                await asyncio.sleep(3)

    async def enviar(self, app_payload: bytes) -> None:
        wire = d.wrap_for_wire(
            dest=OUTSTATION_ADDR, src=MASTER_ADDR, from_master=True,
            app_payload=app_payload, transport_seq=self.siguiente_transport_seq(),
        )
        self.writer.write(wire)
        await self.writer.drain()

    async def receptor(self) -> None:
        buffer = bytearray()
        while True:
            datos = await self.reader.read(4096)
            if not datos:
                raise ConnectionError("el outstation cerro la conexion")
            buffer += datos

            while True:
                try:
                    resultado = d.unwrap_from_wire(bytes(buffer))
                except ValueError as exc:
                    log.error("trama DNP3 invalida, descartando buffer: %s", exc)
                    buffer.clear()
                    break

                if resultado is None:
                    break

                msg, consumidos = resultado
                del buffer[:consumidos]

                if msg.function == d.FC_RESPONSE:
                    await self.response_queue.put(msg)
                elif msg.function == d.FC_UNSOLICITED_RESPONSE:
                    await self.procesar_unsolicited(msg)
                else:
                    log.warning("mensaje inesperado del outstation: %#x", msg.function)

    async def procesar_unsolicited(self, msg: d.AppMessage) -> None:
        buf = msg.objects
        group, _var, _qual, start, stop = buf[0], buf[1], buf[2], buf[3], buf[4]
        pos = 5
        zonas_afectadas = set()

        if group == d.GROUP_BINARY_INPUT:
            for idx in range(start, stop + 1):
                valor = d.decode_binary_flag(buf[pos])
                pos += 1
                zona, cual = divmod(idx, 2)
                if cual == 0:
                    self.snapshot.alarma_baja[zona] = valor
                else:
                    self.snapshot.alarma_encharcamiento[zona] = valor
                zonas_afectadas.add(zona)

        log.warning(
            "<- UNSOLICITED_RESPONSE seq=%d SIN HABER SIDO PEDIDA (%s)",
            msg.control.seq, ", ".join(NOMBRES_ZONAS[z] for z in zonas_afectadas),
        )

        confirm = d.build_app_message(d.FC_CONFIRM, seq=msg.control.seq, uns=True)
        await self.enviar(confirm)
        log.info("-> CONFIRM enviado (seq=%d)", msg.control.seq)

    def _actualizar_snapshot(self, buf: bytes) -> None:
        pos = 0
        while pos < len(buf):
            group, _var, _qual, start, stop = buf[pos], buf[pos + 1], buf[pos + 2], buf[pos + 3], buf[pos + 4]
            pos += 5
            n = stop - start + 1

            if group == d.GROUP_BINARY_INPUT:
                for i in range(n):
                    zona, cual = divmod(start + i, 2)
                    valor = d.decode_binary_flag(buf[pos]); pos += 1
                    (self.snapshot.alarma_baja if cual == 0 else self.snapshot.alarma_encharcamiento)[zona] = valor
            elif group == d.GROUP_BINARY_OUTPUT_STATUS:
                for i in range(n):
                    zona, cual = divmod(start + i, 2)
                    valor = d.decode_binary_flag(buf[pos]); pos += 1
                    (self.snapshot.valvula if cual == 0 else self.snapshot.modo_manual)[zona] = valor
            elif group == d.GROUP_ANALOG_INPUT:
                for i in range(n):
                    zona, cual = divmod(start + i, 2)
                    valor = d.decode_analog_float(buf[pos:pos + 5]); pos += 5
                    (self.snapshot.humedad if cual == 0 else self.snapshot.caudal)[zona] = valor
            elif group == d.GROUP_ANALOG_OUTPUT_STATUS:
                for i in range(n):
                    zona, cual = divmod(start + i, 2)
                    valor = d.decode_ao_status16(buf[pos:pos + 3]); pos += 3
                    (self.snapshot.umbral_min if cual == 0 else self.snapshot.umbral_max)[zona] = valor
            else:
                raise ValueError(f"grupo inesperado en RESPONSE: {group}")

    async def leer_class0(self) -> None:
        seq = self.siguiente_seq()
        app = d.build_app_message(d.FC_READ, seq=seq, objects=d.obj_header_class0_poll())
        await self.enviar(app)
        msg = await asyncio.wait_for(self.response_queue.get(), timeout=5)
        self._actualizar_snapshot(msg.objects)

    async def operar_valvula(self, zona: int, abierta: bool) -> None:
        seq = self.siguiente_seq()
        index = zona * 2
        op = d.CROB_OP_LATCH_ON if abierta else d.CROB_OP_LATCH_OFF
        objs = d.obj_header_count_prefix(d.GROUP_CROB, d.VAR_CROB, count=1) + bytes([index]) + d.encode_crob(op)
        app = d.build_app_message(d.FC_DIRECT_OPERATE, seq=seq, objects=objs)
        await self.enviar(app)
        await asyncio.wait_for(self.response_queue.get(), timeout=5)
        self.snapshot.valvula[zona] = abierta

    async def bucle_control(self) -> None:
        while True:
            await self.leer_class0()

            for zona in range(N_ZONAS):
                s = self.snapshot
                if s.modo_manual[zona]:
                    modo_txt = "MANUAL (SCADA no interviene)"
                else:
                    nueva = s.valvula[zona]
                    if s.humedad[zona] <= s.umbral_min[zona]:
                        nueva = True
                    elif s.humedad[zona] >= s.umbral_max[zona]:
                        nueva = False
                    if nueva != s.valvula[zona]:
                        await self.operar_valvula(zona, nueva)
                    modo_txt = "AUTOMATICO"

                log.info(
                    "[%s] modo=%s humedad=%5.1f%% caudal=%3.0f L/min umbrales=[%d-%d] valvula=%-7s "
                    "alarma_baja=%s encharcamiento=%s",
                    NOMBRES_ZONAS[zona], modo_txt, s.humedad[zona], s.caudal[zona],
                    s.umbral_min[zona], s.umbral_max[zona],
                    "ABIERTA" if s.valvula[zona] else "CERRADA",
                    s.alarma_baja[zona], s.alarma_encharcamiento[zona],
                )

            await asyncio.sleep(POLL_SECONDS)


async def main() -> None:
    while True:
        m = MasterDNP3()
        await m.conectar_con_reintento()

        tareas = [asyncio.create_task(m.receptor()), asyncio.create_task(m.bucle_control())]
        try:
            done, pending = await asyncio.wait(tareas, return_when=asyncio.FIRST_EXCEPTION)
            for t in done:
                exc = t.exception()
                if exc:
                    raise exc
        except (ConnectionError, OSError, asyncio.TimeoutError) as exc:
            log.error("conexion perdida (%s), reconectando...", exc)
        finally:
            for t in tareas:
                t.cancel()
            if m.writer is not None:
                m.writer.close()
            await asyncio.sleep(1)


if __name__ == "__main__":
    asyncio.run(main())
