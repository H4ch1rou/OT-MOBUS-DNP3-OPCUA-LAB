"""
HMI web UNIFICADA de los laboratorios OT (Modbus TCP, DNP3, OPC UA).

Un solo sitio, un solo puerto: cada protocolo vive bajo su propio prefijo
de URL (`/modbus`, `/dnp3`, `/opcua`), pero comparten el mismo dashboard
(plantilla `dashboard.html`) y la misma forma de API REST
(`/<protocolo>/api/estado`, `/<protocolo>/api/zonas/<id>/...`). Lo unico
que cambia entre protocolos es COMO esta aplicacion le habla al equipo de
campo por debajo:

  - Modbus: `pymodbus` (lectura/escritura de coils y holding registers).
  - DNP3:   el codec propio `dnp3lib.py` (READ/DIRECT_OPERATE a mano).
  - OPC UA: `asyncua.sync` (lectura/escritura directa de variables del
            espacio de nodos).

El menu lateral (en `base.html`) lista los tres protocolos, cada uno con
su Dashboard, su documentacion y sus laboratorios -- todo bajo el mismo
origen/puerto, sin enlaces cruzados entre sitios distintos.
"""

import os
import socket
import threading

import markdown as md
from asyncua.sync import Client as OpcuaClient
from flask import (
    Flask, abort, jsonify, redirect, render_template, request, session, url_for,
)
from pymodbus.client import ModbusTcpClient

import dnp3lib as d

app = Flask(__name__)

# ------------------------------------------------------------
# Acceso docente (solucionario protegido por contraseña)
# ------------------------------------------------------------
# El solucionario/pauta de cada protocolo queda detras de un login simple.
# Usuario y clave son configurables por variable de entorno; se dan por
# defecto para que el laboratorio funcione "out of the box", pero se
# recomienda cambiarlos en docker-compose.yml.
app.secret_key = os.environ.get("SECRET_KEY", "agroriego-cambia-esta-clave-secreta")
SOLUCIONARIO_USUARIO = os.environ.get("SOLUCIONARIO_USUARIO", "docente")
SOLUCIONARIO_PASSWORD = os.environ.get("SOLUCIONARIO_PASSWORD", "riego2024")

# Slugs de documento que exigen sesion docente iniciada.
SLUGS_PROTEGIDOS = {"solucionario"}


def _sesion_docente_activa() -> bool:
    return bool(session.get("autenticado"))


ZONAS = [
    "Zona 1 - Parronal",
    "Zona 2 - Hortalizas",
    "Zona 3 - Frutales",
    "Zona 4 - Vivero",
]
N_ZONAS = len(ZONAS)

DOCS_DIR = os.environ.get("DOCS_DIR", "/app/docs")


def zona_o_404(zona_id: int) -> int:
    indice = zona_id - 1
    if not (0 <= indice < N_ZONAS):
        abort(404, description="zona inexistente")
    return indice


def leer_markdown_o_404(ruta_relativa: str) -> str:
    ruta = os.path.join(DOCS_DIR, ruta_relativa)
    with open(ruta, encoding="utf-8") as f:
        return f.read()


# ============================================================
# Backend Modbus TCP
# ============================================================

MODBUS_HOST = os.environ.get("MODBUS_HOST", "modbus-slave")
MODBUS_PORT = int(os.environ.get("MODBUS_PORT", "502"))
MODBUS_UNIT_ID = int(os.environ.get("MODBUS_UNIT_ID", "1"))
MODBUS_HR_STRIDE = 10
MODBUS_DI_STRIDE = 2

_modbus_lock = threading.Lock()
_modbus_client = ModbusTcpClient(MODBUS_HOST, port=MODBUS_PORT)


def _modbus_get_client() -> ModbusTcpClient:
    if not _modbus_client.connected:
        _modbus_client.connect()
    return _modbus_client


def modbus_leer_zonas():
    with _modbus_lock:
        c = _modbus_get_client()
        coils_rr = c.read_coils(0, count=2 * N_ZONAS, slave=MODBUS_UNIT_ID)
        if coils_rr.isError():
            raise ConnectionError("no se pudieron leer las coils del RTU Modbus")

        zonas_out = []
        for i in range(N_ZONAS):
            datos = c.read_holding_registers(i * MODBUS_HR_STRIDE, count=4, slave=MODBUS_UNIT_ID)
            alarmas = c.read_discrete_inputs(i * MODBUS_DI_STRIDE, count=2, slave=MODBUS_UNIT_ID)
            if datos.isError() or alarmas.isError():
                raise ConnectionError(f"no se pudo leer la zona {i + 1} del RTU Modbus")

            humedad, caudal, umbral_min, umbral_max = datos.registers
            zonas_out.append({
                "humedad": humedad, "caudal": caudal,
                "umbral_min": umbral_min, "umbral_max": umbral_max,
                "valvula": bool(coils_rr.bits[i]),
                "modo_manual": bool(coils_rr.bits[N_ZONAS + i]),
                "alarma_baja": bool(alarmas.bits[0]),
                "alarma_encharcamiento": bool(alarmas.bits[1]),
            })
        return zonas_out


def modbus_operar_valvula(zona: int, abierta: bool) -> None:
    with _modbus_lock:
        c = _modbus_get_client()
        c.write_coil(N_ZONAS + zona, True, slave=MODBUS_UNIT_ID)  # modo manual
        c.write_coil(zona, abierta, slave=MODBUS_UNIT_ID)


def modbus_operar_modo(zona: int, manual: bool) -> None:
    with _modbus_lock:
        _modbus_get_client().write_coil(N_ZONAS + zona, manual, slave=MODBUS_UNIT_ID)


def modbus_operar_umbral_min(zona: int, valor: int) -> None:
    with _modbus_lock:
        _modbus_get_client().write_register(zona * MODBUS_HR_STRIDE + 2, valor, slave=MODBUS_UNIT_ID)


def modbus_operar_umbral_max(zona: int, valor: int) -> None:
    with _modbus_lock:
        _modbus_get_client().write_register(zona * MODBUS_HR_STRIDE + 3, valor, slave=MODBUS_UNIT_ID)


# ============================================================
# Backend DNP3
# ============================================================

DNP3_HOST = os.environ.get("DNP3_HOST", "dnp3-outstation")
DNP3_PORT = int(os.environ.get("DNP3_PORT", str(d.DEFAULT_PORT)))
DNP3_MASTER_ADDR = int(os.environ.get("DNP3_MASTER_ADDR", "1"))
DNP3_OUTSTATION_ADDR = int(os.environ.get("DNP3_OUTSTATION_ADDR", "10"))

_dnp3_lock = threading.Lock()
_dnp3_sock: socket.socket | None = None
_dnp3_seq = 0
_dnp3_transport_seq = 0


def _dnp3_siguiente_seq() -> int:
    global _dnp3_seq
    s = _dnp3_seq
    _dnp3_seq = (_dnp3_seq + 1) % 16
    return s


def _dnp3_siguiente_transport_seq() -> int:
    global _dnp3_transport_seq
    s = _dnp3_transport_seq
    _dnp3_transport_seq = (_dnp3_transport_seq + 1) % 64
    return s


def _dnp3_get_socket() -> socket.socket:
    global _dnp3_sock
    if _dnp3_sock is None:
        _dnp3_sock = socket.create_connection((DNP3_HOST, DNP3_PORT), timeout=5)
        _dnp3_sock.settimeout(5)
    return _dnp3_sock


def _dnp3_reset_socket() -> None:
    global _dnp3_sock
    if _dnp3_sock is not None:
        try:
            _dnp3_sock.close()
        except OSError:
            pass
    _dnp3_sock = None


def _dnp3_enviar_y_recibir(app_payload: bytes) -> d.AppMessage:
    """Si llega una UNSOLICITED_RESPONSE mientras esperamos nuestra propia
    RESPONSE, se confirma y se sigue esperando -- si no, se rompe la
    correlacion pedido/respuesta (ver dnp3/PROTOCOLO-DNP3.md)."""
    sock = _dnp3_get_socket()
    wire = d.wrap_for_wire(
        dest=DNP3_OUTSTATION_ADDR, src=DNP3_MASTER_ADDR, from_master=True,
        app_payload=app_payload, transport_seq=_dnp3_siguiente_transport_seq(),
    )
    sock.sendall(wire)

    buffer = bytearray()
    while True:
        resultado = d.unwrap_from_wire(bytes(buffer))
        if resultado is None:
            datos = sock.recv(4096)
            if not datos:
                raise ConnectionError("el outstation DNP3 cerro la conexion")
            buffer += datos
            continue

        msg, consumidos = resultado
        del buffer[:consumidos]

        if msg.function == d.FC_UNSOLICITED_RESPONSE:
            confirm = d.build_app_message(d.FC_CONFIRM, seq=msg.control.seq, uns=True)
            confirm_wire = d.wrap_for_wire(
                dest=DNP3_OUTSTATION_ADDR, src=DNP3_MASTER_ADDR, from_master=True,
                app_payload=confirm, transport_seq=_dnp3_siguiente_transport_seq(),
            )
            sock.sendall(confirm_wire)
            continue

        return msg


def _dnp3_con_reintento(func, *args, **kwargs):
    try:
        return func(*args, **kwargs)
    except (ConnectionError, OSError, TimeoutError):
        _dnp3_reset_socket()
        return func(*args, **kwargs)


def dnp3_leer_zonas():
    def _leer():
        with _dnp3_lock:
            seq = _dnp3_siguiente_seq()
            app_msg = d.build_app_message(d.FC_READ, seq=seq, objects=d.obj_header_class0_poll())
            msg = _dnp3_enviar_y_recibir(app_msg)

        zonas = [
            {"humedad": 0, "caudal": 0, "umbral_min": 0, "umbral_max": 0, "valvula": False, "modo_manual": False,
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
                    zonas[zona]["humedad" if cual == 0 else "caudal"] = round(valor)
                elif group == d.GROUP_ANALOG_OUTPUT_STATUS:
                    valor = d.decode_ao_status16(buf[pos:pos + 3]); pos += 3
                    zonas[zona]["umbral_min" if cual == 0 else "umbral_max"] = valor
        return zonas

    return _dnp3_con_reintento(_leer)


def dnp3_operar_crob(indice_punto: int, activar: bool) -> None:
    def _op():
        with _dnp3_lock:
            seq = _dnp3_siguiente_seq()
            op = d.CROB_OP_LATCH_ON if activar else d.CROB_OP_LATCH_OFF
            objs = d.obj_header_count_prefix(d.GROUP_CROB, d.VAR_CROB, count=1) + bytes([indice_punto]) + d.encode_crob(op)
            app_msg = d.build_app_message(d.FC_DIRECT_OPERATE, seq=seq, objects=objs)
            _dnp3_enviar_y_recibir(app_msg)

    _dnp3_con_reintento(_op)


def dnp3_operar_analog_output(indice_punto: int, valor: int) -> None:
    def _op():
        with _dnp3_lock:
            seq = _dnp3_siguiente_seq()
            objs = d.obj_header_count_prefix(d.GROUP_ANALOG_OUTPUT_COMMAND, d.VAR_ANALOG_OUTPUT_COMMAND_16, count=1) + \
                bytes([indice_punto]) + d.encode_ao_command16(valor)
            app_msg = d.build_app_message(d.FC_DIRECT_OPERATE, seq=seq, objects=objs)
            _dnp3_enviar_y_recibir(app_msg)

    _dnp3_con_reintento(_op)


def dnp3_operar_valvula(zona: int, abierta: bool) -> None:
    dnp3_operar_crob(zona * 2 + 1, True)   # modo manual = True
    dnp3_operar_crob(zona * 2, abierta)     # valvula


def dnp3_operar_modo(zona: int, manual: bool) -> None:
    dnp3_operar_crob(zona * 2 + 1, manual)


def dnp3_operar_umbral_min(zona: int, valor: int) -> None:
    dnp3_operar_analog_output(zona * 2, valor)


def dnp3_operar_umbral_max(zona: int, valor: int) -> None:
    dnp3_operar_analog_output(zona * 2 + 1, valor)


# ============================================================
# Backend OPC UA
# ============================================================

OPCUA_HOST = os.environ.get("OPCUA_HOST", "opcua-server")
OPCUA_PORT = int(os.environ.get("OPCUA_PORT", "4840"))
OPCUA_URL = f"opc.tcp://{OPCUA_HOST}:{OPCUA_PORT}/riego/server/"
OPCUA_NS_URI = "http://riego.local/"
OPCUA_NODOS_NOMBRES = ["Zona1", "Zona2", "Zona3", "Zona4"]

_opcua_lock = threading.Lock()
_opcua_client: OpcuaClient | None = None
_opcua_zonas: list[dict] | None = None


def _opcua_conectar() -> None:
    global _opcua_client, _opcua_zonas
    client = OpcuaClient(url=OPCUA_URL)
    client.connect()
    idx = client.get_namespace_index(OPCUA_NS_URI)
    objects = client.get_objects_node()

    zonas = []
    for nombre_nodo in OPCUA_NODOS_NOMBRES:
        obj = objects.get_child([f"{idx}:Zonas", f"{idx}:{nombre_nodo}"])
        zonas.append({
            "humedad": obj.get_child(f"{idx}:Humedad"),
            "caudal": obj.get_child(f"{idx}:Caudal"),
            "umbral_min": obj.get_child(f"{idx}:UmbralMinimo"),
            "umbral_max": obj.get_child(f"{idx}:UmbralMaximo"),
            "valvula": obj.get_child(f"{idx}:Valvula"),
            "modo_manual": obj.get_child(f"{idx}:ModoManual"),
            "alarma_baja": obj.get_child(f"{idx}:AlarmaBaja"),
            "alarma_encharcamiento": obj.get_child(f"{idx}:AlarmaEncharcamiento"),
        })

    _opcua_client = client
    _opcua_zonas = zonas


def _opcua_get_zonas() -> list[dict]:
    if _opcua_client is None:
        _opcua_conectar()
    return _opcua_zonas


def _opcua_reset() -> None:
    global _opcua_client, _opcua_zonas
    if _opcua_client is not None:
        try:
            _opcua_client.disconnect()
        except Exception:
            pass
    _opcua_client = None
    _opcua_zonas = None


def _opcua_con_reintento(func, *args, **kwargs):
    try:
        return func(*args, **kwargs)
    except Exception:
        _opcua_reset()
        return func(*args, **kwargs)


def opcua_leer_zonas():
    def _leer():
        with _opcua_lock:
            zonas = _opcua_get_zonas()
            out = []
            for z in zonas:
                out.append({
                    "humedad": round(z["humedad"].read_value()),
                    "caudal": round(z["caudal"].read_value()),
                    "umbral_min": round(z["umbral_min"].read_value()),
                    "umbral_max": round(z["umbral_max"].read_value()),
                    "valvula": bool(z["valvula"].read_value()),
                    "modo_manual": bool(z["modo_manual"].read_value()),
                    "alarma_baja": bool(z["alarma_baja"].read_value()),
                    "alarma_encharcamiento": bool(z["alarma_encharcamiento"].read_value()),
                })
            return out

    return _opcua_con_reintento(_leer)


def opcua_operar_valvula(zona: int, abierta: bool) -> None:
    def _op():
        with _opcua_lock:
            z = _opcua_get_zonas()[zona]
            z["modo_manual"].write_value(True)
            z["valvula"].write_value(bool(abierta))

    _opcua_con_reintento(_op)


def opcua_operar_modo(zona: int, manual: bool) -> None:
    def _op():
        with _opcua_lock:
            _opcua_get_zonas()[zona]["modo_manual"].write_value(bool(manual))

    _opcua_con_reintento(_op)


def opcua_operar_umbral_min(zona: int, valor: int) -> None:
    def _op():
        with _opcua_lock:
            _opcua_get_zonas()[zona]["umbral_min"].write_value(float(valor))

    _opcua_con_reintento(_op)


def opcua_operar_umbral_max(zona: int, valor: int) -> None:
    def _op():
        with _opcua_lock:
            _opcua_get_zonas()[zona]["umbral_max"].write_value(float(valor))

    _opcua_con_reintento(_op)


# ============================================================
# Registro de protocolos: docs, laboratorios, backend y textos
# ============================================================

FOOTER_MODBUS = """
Cada control de esta pagina genera una transaccion Modbus TCP real hacia el
RTU de campo (<code>{host}:{port}</code>): lectura con funciones 0x01/0x02/0x03
y escritura con 0x05/0x06, sobre la coil y los registros propios de cada
zona. No hay ninguna autenticacion. Para observar el trafico, entra al
contenedor de captura (<code>docker exec -it modbus-sniffer sh</code>) y
corre <code>tcpdump -i any -n -A 'tcp port 502'</code>, o analiza despues
<code>modbus/captures/modbus.pcap</code> con Wireshark.
""".strip()

FOOTER_DNP3 = """
Cada control de esta pagina genera una transaccion DNP3 real hacia el
outstation de campo (<code>{host}:{port}</code>): lectura con READ
(integrity poll) y escritura con DIRECT_OPERATE (CROB / Analog Output).
No hay ninguna autenticacion. Ademas, a diferencia de Modbus, el
outstation puede mandar UNSOLICITED_RESPONSE por su cuenta cuando una
alarma cambia. Para observar el trafico, entra al contenedor de captura
(<code>docker exec -it dnp3-sniffer sh</code>) y corre
<code>tcpdump -i any -n -A 'tcp port 20000'</code>, o analiza despues
<code>dnp3/captures/dnp3.pcap</code> con Wireshark.
""".strip()

FOOTER_OPCUA = """
Cada control de esta pagina genera una transaccion OPC UA real hacia el
servidor de campo (<code>{host}:{port}</code>): lectura/escritura directa
de variables del espacio de nodos (sin objetos de comando como el CROB de
DNP3). No hay ninguna autenticacion (sesion anonima, sin seguridad). OPC
UA ademas ofrece <em>Subscriptions</em> nativas -- el SCADA de este
laboratorio esta suscrito a las alarmas y se entera de sus cambios sin
hacer polling. Para observar el trafico, entra al contenedor de captura
(<code>docker exec -it opcua-sniffer sh</code>) y corre
<code>tcpdump -i any -n -A 'tcp port 4840'</code>, o analiza despues
<code>opcua/captures/opcua.pcap</code> con Wireshark.
""".strip()


def _docs_estandar(prefix: str, nombre_doc_protocolo: str, archivo_protocolo: str):
    return [
        {"slug": "guia-laboratorio", "title": "Guia del laboratorio", "file": f"{prefix}/README.md"},
        {"slug": f"protocolo-{prefix}", "title": nombre_doc_protocolo, "file": f"{prefix}/{archivo_protocolo}"},
        {"slug": "indice-protocolos", "title": "Indice de protocolos", "file": "INDICE-PROTOCOLOS.md"},
    ]


def _labs_estandar(prefix: str, lab_files: list[str], lab_titles: list[str]):
    labs = [{"slug": "laboratorios", "title": "Indice de laboratorios", "file": f"{prefix}/laboratorios/README.md"}]
    for i, (archivo, titulo) in enumerate(zip(lab_files, lab_titles), start=1):
        labs.append({"slug": f"lab{i}", "title": titulo, "file": f"{prefix}/laboratorios/{archivo}"})
    return labs


def _solucionario_estandar(prefix: str):
    # Un unico documento protegido por protocolo: la pauta docente, que trae
    # el resultado esperado y el paso a paso de resolucion de los 3 labs.
    return [
        {
            "slug": "solucionario",
            "title": "Pauta y solucionario (labs 1-3)",
            "file": f"{prefix}/laboratorios/pauta-docente.md",
        },
    ]


PROTOCOLOS = {
    "modbus": {
        "nombre": "Modbus TCP",
        "descripcion": "El protocolo OT mas simple y difundido. Solo lectura/escritura por polling: el esclavo nunca habla si nadie le pregunta.",
        "host": MODBUS_HOST, "port": MODBUS_PORT,
        "leer_zonas": modbus_leer_zonas,
        "operar_valvula": modbus_operar_valvula,
        "operar_modo": modbus_operar_modo,
        "operar_umbral_min": modbus_operar_umbral_min,
        "operar_umbral_max": modbus_operar_umbral_max,
        "footer": FOOTER_MODBUS,
        "docs": _docs_estandar("modbus", "Protocolo Modbus", "PROTOCOLO-MODBUS.md"),
        "labs": _labs_estandar(
            "modbus",
            ["lab-1-reconocimiento-pasivo.md", "lab-2-escritura-actuadores.md", "lab-3-manipulacion-setpoints.md"],
            ["Lab 1 - Reconocimiento pasivo", "Lab 2 - Escritura de actuadores", "Lab 3 - Manipulacion de setpoints"],
        ),
    },
    "dnp3": {
        "nombre": "DNP3",
        "descripcion": "Muy usado en electricidad/agua. Tres capas de protocolo, y el outstation SI puede avisar cambios por su cuenta.",
        "host": DNP3_HOST, "port": DNP3_PORT,
        "leer_zonas": dnp3_leer_zonas,
        "operar_valvula": dnp3_operar_valvula,
        "operar_modo": dnp3_operar_modo,
        "operar_umbral_min": dnp3_operar_umbral_min,
        "operar_umbral_max": dnp3_operar_umbral_max,
        "footer": FOOTER_DNP3,
        "docs": _docs_estandar("dnp3", "Protocolo DNP3", "PROTOCOLO-DNP3.md"),
        "labs": _labs_estandar(
            "dnp3",
            ["lab-1-integrity-poll-unsolicited.md", "lab-2-control-direct-operate.md", "lab-3-manipulacion-setpoints.md"],
            ["Lab 1 - Integrity poll y unsolicited", "Lab 2 - Control por DIRECT_OPERATE", "Lab 3 - Manipulacion de setpoints"],
        ),
    },
    "opcua": {
        "nombre": "OPC UA",
        "descripcion": "Protocolo moderno orientado a servicios, con modelo de nodos rico y Subscriptions nativas para avisos push.",
        "host": OPCUA_HOST, "port": OPCUA_PORT,
        "leer_zonas": opcua_leer_zonas,
        "operar_valvula": opcua_operar_valvula,
        "operar_modo": opcua_operar_modo,
        "operar_umbral_min": opcua_operar_umbral_min,
        "operar_umbral_max": opcua_operar_umbral_max,
        "footer": FOOTER_OPCUA,
        "docs": _docs_estandar("opcua", "Protocolo OPC UA", "PROTOCOLO-OPCUA.md"),
        "labs": _labs_estandar(
            "opcua",
            ["lab-1-subscriptions.md", "lab-2-escritura-directa-variables.md", "lab-3-manipulacion-setpoints.md"],
            ["Lab 1 - Subscriptions (avisos push)", "Lab 2 - Escritura directa de variables", "Lab 3 - Manipulacion de setpoints"],
        ),
    },
}

# Reescritura de enlaces relativos de los .md originales a rutas web
# equivalentes (/<protocolo>/docs/<slug>), namespaced por protocolo.
DOC_LINK_REWRITES = {}
for _prefix, _cfg in PROTOCOLOS.items():
    _up = _prefix.upper()
    DOC_LINK_REWRITES[(_prefix, "guia-laboratorio")] = {
        "(../README.md)": "(/{}/docs/indice-protocolos)".format(_prefix),
        f"(PROTOCOLO-{_up}.md)": f"(/{_prefix}/docs/protocolo-{_prefix})",
        "(laboratorios/README.md)": f"(/{_prefix}/docs/laboratorios)",
    }
    DOC_LINK_REWRITES[(_prefix, f"protocolo-{_prefix}")] = {
        "(README.md)": f"(/{_prefix}/docs/guia-laboratorio)",
        "(../README.md)": f"(/{_prefix}/docs/indice-protocolos)",
    }
    DOC_LINK_REWRITES[(_prefix, "laboratorios")] = {
        "(../README.md)": f"(/{_prefix}/docs/guia-laboratorio)",
        f"(../PROTOCOLO-{_up}.md)": f"(/{_prefix}/docs/protocolo-{_prefix})",
        **{
            f"({item['file'].split('/')[-1]})": f"(/{_prefix}/docs/{item['slug']})"
            for item in _cfg["labs"] if item["slug"] != "laboratorios"
        },
    }
    DOC_LINK_REWRITES[(_prefix, "indice-protocolos")] = {
        f"(modbus/README.md)": "(/modbus/docs/guia-laboratorio)",
        f"(modbus/PROTOCOLO-MODBUS.md)": "(/modbus/docs/protocolo-modbus)",
        f"(modbus/laboratorios/README.md)": "(/modbus/docs/laboratorios)",
        f"(dnp3/README.md)": "(/dnp3/docs/guia-laboratorio)",
        f"(dnp3/PROTOCOLO-DNP3.md)": "(/dnp3/docs/protocolo-dnp3)",
        f"(dnp3/laboratorios/README.md)": "(/dnp3/docs/laboratorios)",
        f"(opcua/README.md)": "(/opcua/docs/guia-laboratorio)",
        f"(opcua/PROTOCOLO-OPCUA.md)": "(/opcua/docs/protocolo-opcua)",
        f"(opcua/laboratorios/README.md)": "(/opcua/docs/laboratorios)",
    }

# Casos especiales: los 3 README.md se enlazan directamente entre si (no
# solo via el indice general).
DOC_LINK_REWRITES[("modbus", "guia-laboratorio")]["(../dnp3/README.md)"] = "(/dnp3/docs/guia-laboratorio)"
DOC_LINK_REWRITES[("modbus", "guia-laboratorio")]["(../opcua/README.md)"] = "(/opcua/docs/guia-laboratorio)"
DOC_LINK_REWRITES[("dnp3", "guia-laboratorio")]["(../modbus/README.md)"] = "(/modbus/docs/guia-laboratorio)"
DOC_LINK_REWRITES[("dnp3", "guia-laboratorio")]["(../opcua/README.md)"] = "(/opcua/docs/guia-laboratorio)"
DOC_LINK_REWRITES[("opcua", "guia-laboratorio")]["(../modbus/README.md)"] = "(/modbus/docs/guia-laboratorio)"
DOC_LINK_REWRITES[("opcua", "guia-laboratorio")]["(../dnp3/README.md)"] = "(/dnp3/docs/guia-laboratorio)"

# El solucionario (pauta docente) se registra por protocolo, aparte de docs
# y labs, para poder protegerlo con contraseña.
for _prefix, _cfg in PROTOCOLOS.items():
    _cfg["solucionario"] = _solucionario_estandar(_prefix)


DOCS_BY_SLUG = {
    prefix: {item["slug"]: item for item in cfg["docs"] + cfg["labs"] + cfg["solucionario"]}
    for prefix, cfg in PROTOCOLOS.items()
}


NAV_PROTOCOLOS = [
    {
        "prefix": prefix,
        "nombre": cfg["nombre"],
        "descripcion": cfg["descripcion"],
        "docs": cfg["docs"],
        "labs": cfg["labs"],
        "solucionario": cfg["solucionario"],
    }
    for prefix, cfg in PROTOCOLOS.items()
]


@app.context_processor
def inject_nav():
    # protocolo_actual se pasa por cada ruta via render_template(); esto
    # solo asegura un valor por defecto para plantillas que no lo pasen.
    return {
        "protocolos_nav": NAV_PROTOCOLOS,
        "protocolo_actual": None,
        "autenticado": _sesion_docente_activa(),
    }


# ============================================================
# Rutas
# ============================================================

@app.route("/")
def landing():
    return render_template("landing.html", protocolo_actual=None, active_doc=None)


@app.route("/<protocolo>/")
def dashboard(protocolo: str):
    if protocolo not in PROTOCOLOS:
        abort(404)
    cfg = PROTOCOLOS[protocolo]
    return render_template(
        "dashboard.html",
        prefix=protocolo,
        nombre_protocolo=cfg["nombre"],
        host=cfg["host"], port=cfg["port"],
        footer_html=cfg["footer"].format(host=cfg["host"], port=cfg["port"]),
        zonas=list(enumerate(ZONAS, start=1)),
        protocolo_actual=protocolo,
        active_doc=None,
    )


@app.route("/login", methods=["GET", "POST"])
def login():
    # A donde volver despues de entrar: solo rutas internas, nunca una URL
    # externa (evita "open redirect").
    destino = request.values.get("next") or "/"
    if not destino.startswith("/") or destino.startswith("//"):
        destino = "/"

    error = None
    if request.method == "POST":
        usuario = request.form.get("usuario", "")
        clave = request.form.get("clave", "")
        if usuario == SOLUCIONARIO_USUARIO and clave == SOLUCIONARIO_PASSWORD:
            session["autenticado"] = True
            return redirect(destino)
        error = "Usuario o contraseña incorrectos."

    return render_template(
        "login.html", error=error, next=destino,
        protocolo_actual=None, active_doc=None,
    )


@app.route("/logout")
def logout():
    session.pop("autenticado", None)
    return redirect("/")


@app.route("/<protocolo>/docs/<slug>")
def doc_page(protocolo: str, slug: str):
    if protocolo not in PROTOCOLOS:
        abort(404)

    # Documentos protegidos (solucionario): exigen sesion docente.
    if slug in SLUGS_PROTEGIDOS and not _sesion_docente_activa():
        return redirect(url_for("login", next=request.path))

    entrada = DOCS_BY_SLUG[protocolo].get(slug)
    if entrada is None:
        abort(404, description="documento inexistente")

    try:
        texto = leer_markdown_o_404(entrada["file"])
    except OSError:
        return (
            f"<p>No se pudo leer <code>{entrada['file']}</code>. "
            "Verifica que docker-compose.yml este montando la carpeta de "
            "documentacion en el servicio webhmi.</p>",
            404,
        )

    for viejo, nuevo in DOC_LINK_REWRITES.get((protocolo, slug), {}).items():
        texto = texto.replace(viejo, nuevo)

    contenido_html = md.markdown(texto, extensions=["tables", "fenced_code", "toc"])
    return render_template(
        "doc.html", titulo=entrada["title"], contenido_html=contenido_html,
        protocolo_actual=protocolo, active_doc=slug,
    )


def _leer_entero_body(campo: str) -> int:
    datos = request.get_json(force=True, silent=True) or {}
    return int(datos[campo])


@app.route("/<protocolo>/api/estado")
def api_estado(protocolo: str):
    if protocolo not in PROTOCOLOS:
        abort(404)
    cfg = PROTOCOLOS[protocolo]
    try:
        zonas_datos = cfg["leer_zonas"]()
    except (ConnectionError, OSError, TimeoutError) as exc:
        return jsonify({"error": f"no se pudo leer el equipo de campo: {exc}"}), 502

    zonas_out = [{"id": i + 1, "nombre": ZONAS[i], **z} for i, z in enumerate(zonas_datos)]
    return jsonify({"zonas": zonas_out})


@app.route("/<protocolo>/api/zonas/<int:zona_id>/valvula", methods=["POST"])
def api_valvula(protocolo: str, zona_id: int):
    if protocolo not in PROTOCOLOS:
        abort(404)
    zona = zona_o_404(zona_id)
    datos = request.get_json(force=True, silent=True) or {}
    abierta = bool(datos.get("abierta"))
    PROTOCOLOS[protocolo]["operar_valvula"](zona, abierta)
    return jsonify({"ok": True, "zona": zona_id, "valvula": abierta, "modo_manual": True})


@app.route("/<protocolo>/api/zonas/<int:zona_id>/modo", methods=["POST"])
def api_modo(protocolo: str, zona_id: int):
    if protocolo not in PROTOCOLOS:
        abort(404)
    zona = zona_o_404(zona_id)
    datos = request.get_json(force=True, silent=True) or {}
    manual = bool(datos.get("manual"))
    PROTOCOLOS[protocolo]["operar_modo"](zona, manual)
    return jsonify({"ok": True, "zona": zona_id, "modo_manual": manual})


@app.route("/<protocolo>/api/zonas/<int:zona_id>/umbral_min", methods=["POST"])
def api_umbral_min(protocolo: str, zona_id: int):
    if protocolo not in PROTOCOLOS:
        abort(404)
    zona = zona_o_404(zona_id)
    valor = max(0, min(100, _leer_entero_body("valor")))
    PROTOCOLOS[protocolo]["operar_umbral_min"](zona, valor)
    return jsonify({"ok": True, "zona": zona_id, "umbral_min": valor})


@app.route("/<protocolo>/api/zonas/<int:zona_id>/umbral_max", methods=["POST"])
def api_umbral_max(protocolo: str, zona_id: int):
    if protocolo not in PROTOCOLOS:
        abort(404)
    zona = zona_o_404(zona_id)
    valor = max(0, min(100, _leer_entero_body("valor")))
    PROTOCOLOS[protocolo]["operar_umbral_max"](zona, valor)
    return jsonify({"ok": True, "zona": zona_id, "umbral_max": valor})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, threaded=False)
