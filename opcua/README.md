# PoC OPC UA - Central de Riego (Laboratorio OT)

Laboratorio Docker para practicar seguridad OT sobre OPC UA, usando el
**mismo escenario** que los laboratorios [Modbus](../modbus/README.md) y
[DNP3](../dnp3/README.md) (una central de riego con 4 zonas
independientes), para poder comparar los tres protocolos sobre el mismo
proceso fisico. Un servidor OPC UA expone sensores/actuadores como un
espacio de nodos, una central SCADA lo controla automaticamente (usando
ademas Subscriptions nativas para enterarse de alarmas), y el dashboard
web unificado permite a los alumnos intervenir cada zona mientras
observan el trafico con `tcpdump`.

> Este directorio es el laboratorio **OPC UA** dentro del repositorio de
> protocolos OT. Ver el [indice general](../README.md) para otros
> protocolos (incluidos [Modbus](../modbus/README.md) y
> [DNP3](../dnp3/README.md)), y [`PROTOCOLO-OPCUA.md`](PROTOCOLO-OPCUA.md)
> para una explicacion del protocolo y una guia paso a paso de como leer
> `captures/opcua.pcap` en Wireshark.

Este laboratorio usa `asyncua`, la libreria OPC UA pura-Python mas
completa y mantenida disponible: a diferencia de DNP3 (donde no existia
una opcion viable y hubo que escribir un codec propio), para OPC UA SI
tiene sentido usar una libreria real, dado lo grande y complejo que es el
protocolo completo (ver `PROTOCOLO-OPCUA.md`).

## Componentes

Todos los servicios de este laboratorio se levantan junto con los otros
dos desde el **`docker-compose.yml` de la raiz del repositorio** (ya no
hay un compose por protocolo -- ver el [README raiz](../README.md)).

| Servicio          | Rol                                                          | Puerto/hostname       |
|--------------------|------------------------------------------------------------------|------------------------|
| `opcua-server`     | Servidor OPC UA: 4 zonas, sensores + actuadores como nodos       | `opcua-server:4840`   |
| `opcua-master`     | Central SCADA (polling + control automatico + Subscription de alarmas) | `opcua-master`  |
| `opcua-operador`   | Consola de operador en terminal, conectada directo al servidor (a demanda) | `opcua-operador` |
| `opcua-sniffer`    | Punto de captura (`tcpdump`), inactivo hasta que el alumno lo activa | -                  |

El **dashboard web** de este laboratorio (igual que Modbus y DNP3) vive
en el sitio unificado: `http://localhost:9090/opcua/`.

## Zonas de riego simuladas

Mismas 4 zonas que los otros dos laboratorios: Parronal, Hortalizas,
Frutales, Vivero -- cada una con su propio sensor de humedad, caudal,
umbrales de control y electrovalvula, ahora expuestos como variables OPC
UA (`Humedad`, `Caudal`, `UmbralMinimo`, `UmbralMaximo`, `Valvula`,
`ModoManual`, `AlarmaBaja`, `AlarmaEncharcamiento`) bajo
`Objects/Zonas/Zona1..4`. Ver el arbol completo en `PROTOCOLO-OPCUA.md`.

## Levantar el laboratorio

Desde la **raiz del repositorio** (no desde esta carpeta):

```bash
docker compose up -d --build
```

Esto levanta los tres protocolos (Modbus, DNP3, OPC UA) y el dashboard
web unificado de una sola vez. Todo corre en segundo plano; los
`*-sniffer` arrancan pero se quedan **inactivos** hasta que un alumno
entra a activarlos.

Abre en el navegador:

```
http://localhost:9090/opcua/
```

y usa el menu lateral para moverte entre protocolos, documentacion y
laboratorios sin salir del sitio.

`opcua-operador` (consola de texto, alternativa al dashboard, conectada
directo al servidor) **no** arranca con `up` porque es interactiva:

```bash
docker compose run --rm opcua-operador
```

## Activar el sniffing (a mano, desde dentro del contenedor)

```bash
docker exec -it opcua-sniffer sh
tcpdump -i any -n -A 'tcp port 4840'
```

O, para guardar la captura (queda en el host, en `./opcua/captures/opcua.pcap`):

```bash
tcpdump -i any -n -w /captures/opcua.pcap 'tcp port 4840'
```

### Flujo de trabajo sugerido para la clase

1. `docker compose up -d --build` (desde la raiz del repositorio).
2. Abrir `http://localhost:9090/opcua/`.
3. En otra terminal, entrar al sniffer de OPC UA y lanzar tcpdump.
4. En la pagina web, elegir una zona y presionar "Abrir"/"Cerrar", o
   cambiar un umbral.
5. Ver en la terminal del sniffer los mensajes `Write` (y su respuesta)
   correspondientes.
6. Forzar una zona a modo manual con la valvula cerrada (como en el
   Laboratorio 3) y esperar a que una alarma cambie de estado: deberias
   ver un mensaje `Publish` del **servidor** llegando por su cuenta al
   `opcua-master` -- la Subscription nativa de OPC UA en accion.
7. Abrir `./opcua/captures/opcua.pcap` con Wireshark (filtro `opcua`) y
   revisar el detalle, usando `PROTOCOLO-OPCUA.md` como referencia.

Detener y limpiar (desde la raiz):

```bash
docker compose down
```

## Ideas para extender el laboratorio

- **Falta de seguridad**: a diferencia de Modbus/DNP3, OPC UA SI define
  un modelo de seguridad completo (certificados, cifrado, autenticacion
  de usuario) -- pero este laboratorio lo desactiva a proposito
  (`SecurityPolicy = None`, sesion anonima) para que la comparacion sea
  directa. Discutir que cambiaria en el pcap si se activara seguridad de
  transporte (los Read/Write dejarian de verse en texto plano).
- **Comparar los tres mecanismos de "aviso de cambio"**: Modbus (solo
  polling), DNP3 (unsolicited, hecho a mano), OPC UA (Subscriptions,
  nativas y estandar). ¿Cual es mas facil de detectar/instrumentar desde
  el punto de vista de un defensor?
- **Escritura directa vs objeto de comando**: en Modbus hay coils, en
  DNP3 hay CROB, y en OPC UA se escribe la variable directo. Discutir si
  esto hace a OPC UA mas o menos seguro por diseno frente a escrituras no
  autorizadas.
- **Deteccion**: Wireshark tiene un disector OPC UA nativo; discutir que
  reglas de IDS podrian escribirse para alertar sobre `Write` fuera de
  horario, o sobre sesiones anonimas hacia servidores OPC UA en
  produccion (que deberian exigir autenticacion).
