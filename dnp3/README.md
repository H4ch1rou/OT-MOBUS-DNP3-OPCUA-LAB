# PoC DNP3 - Central de Riego (Laboratorio OT)

Laboratorio Docker para practicar seguridad OT sobre DNP3, usando el
**mismo escenario** que los laboratorios [Modbus](../modbus/README.md) y
[OPC UA](../opcua/README.md) (una central de riego con 4 zonas
independientes) para poder comparar los tres protocolos sobre el mismo
proceso fisico. Un outstation de campo expone sensores/actuadores, una
central SCADA lo controla automaticamente, y el dashboard web unificado
permite a los alumnos intervenir cada zona mientras observan el trafico
con `tcpdump`.

> Este directorio es el laboratorio **DNP3** dentro del repositorio de
> protocolos OT. Ver el [indice general](../README.md) para otros
> protocolos (incluidos [Modbus](../modbus/README.md) y
> [OPC UA](../opcua/README.md)), y [`PROTOCOLO-DNP3.md`](PROTOCOLO-DNP3.md)
> para una explicacion del protocolo y una guia paso a paso de como leer
> `dnp3/captures/dnp3.pcap` en Wireshark.

No existe una libreria DNP3 pura en Python que sea liviana y este
mantenida, asi que este laboratorio usa un **codec DNP3 propio**
(`common/dnp3lib.py`): framing real de las 3 capas del protocolo, con
CRC-16 verificado contra el vector de prueba estandar, y los function
codes/grupos de objetos necesarios para el escenario. El detalle esta en
`PROTOCOLO-DNP3.md`.

## Componentes

Estos servicios se levantan junto con los de Modbus y OPC UA desde el
**`docker-compose.yml` de la raiz del repositorio** (ya no hay un compose
por protocolo -- ver el [README raiz](../README.md)).

| Servicio           | Rol                                                          | Puerto/hostname        |
|---------------------|----------------------------------------------------------------|-------------------------|
| `dnp3-outstation`   | RTU de campo: 4 zonas, sensores + actuadores via DNP3           | `dnp3-outstation:20000` |
| `dnp3-master`       | Central SCADA (integrity poll + control automatico por zona)   | `dnp3-master`           |
| `dnp3-operador`     | Consola de operador en terminal, conectada directo al outstation (a demanda) | `dnp3-operador` |
| `dnp3-sniffer`      | Punto de captura (`tcpdump`), inactivo hasta que el alumno lo activa | -                  |

El **dashboard web** de este laboratorio vive en el sitio unificado:
`http://localhost:9090/dnp3/`.

Todos comparten la red `ot_network` (compartida por los tres protocolos y
el dashboard). Los contenedores se referencian siempre por nombre de
host, nunca por IP fija.

## Zonas de riego simuladas

Mismas 4 zonas que los otros dos laboratorios: Parronal, Hortalizas,
Frutales, Vivero -- cada una con su propio sensor de humedad, caudal,
umbrales de control y electrovalvula, ahora expuestos como puntos DNP3
(Analog Input/Output, Binary Input, Binary Output/CROB) en vez de
registros y coils Modbus. Ver el mapa completo en `PROTOCOLO-DNP3.md`.

## Levantar el laboratorio

Desde la **raiz del repositorio** (no desde esta carpeta):

```bash
docker compose up -d --build
```

Todo corre en segundo plano (`-d`): esto levanta los tres protocolos a la
vez mas el dashboard web unificado; `dnp3-sniffer` arranca pero se queda
**inactivo**, sin capturar nada, hasta que un alumno entra a activarlo.

```bash
docker compose logs dnp3-master   # ver que hizo el SCADA hasta ahora
docker compose ps
```

Abre en el navegador:

```
http://localhost:9090/dnp3/
```

El dashboard es visualmente identico al de Modbus y OPC UA (mismo resumen
general, mismo esquema de zonas, mismas tarjetas por zona), pero cada
boton ahora se traduce en un `READ`/`DIRECT_OPERATE` DNP3 en vez de una
lectura/escritura Modbus. El menu lateral permite navegar tanto la
documentacion/laboratorios de DNP3 como, sin salir del sitio, saltar al
dashboard y documentacion de Modbus u OPC UA.

`dnp3-operador` (consola de texto, alternativa al dashboard, conectada
directo al outstation) **no** arranca con `up` porque es interactiva:

```bash
docker compose run --rm dnp3-operador
```

## Activar el sniffing (a mano, desde dentro del contenedor)

El contenedor `dnp3-sniffer` comparte el namespace de red del outstation
(`network_mode: service:dnp3-outstation`), asi que ve exactamente el
mismo trafico que le llega al equipo de campo. Arranca inactivo a
proposito:

```bash
docker exec -it dnp3-sniffer sh
tcpdump -i any -n -A 'tcp port 20000'
```

O, para guardar la captura (queda en el host, en `dnp3/captures/dnp3.pcap`):

```bash
tcpdump -i any -n -w /captures/dnp3.pcap 'tcp port 20000'
```

### Flujo de trabajo sugerido para la clase

1. `docker compose up -d --build` (desde la raiz del repositorio).
2. Abrir `http://localhost:9090/dnp3/` en el navegador.
3. En otra terminal, entrar al sniffer y lanzar tcpdump.
4. En la pagina web, elegir una zona y presionar "Abrir"/"Cerrar", o
   cambiar un umbral.
5. Ver en la terminal del sniffer los paquetes `DIRECT_OPERATE` (func=5)
   y su `RESPONSE` (func=129) correspondientes.
6. Dejar correr el laboratorio un rato (o forzar una zona a modo manual
   con la valvula cerrada, como en el Laboratorio 3) hasta que una
   alarma cambie de estado, y ver aparecer una `UNSOLICITED_RESPONSE`
   (func=130) **sin que nadie la haya pedido**, seguida de un `CONFIRM`
   del master -- esto no tiene equivalente en el laboratorio Modbus.
7. Abrir `dnp3/captures/dnp3.pcap` con Wireshark (filtro `dnp3`) y revisar
   el detalle completo, usando `PROTOCOLO-DNP3.md` como referencia.

Detener y limpiar (desde la raiz):

```bash
docker compose down
```

## Ideas para extender el laboratorio

- **Falta de autenticacion**: igual que en Modbus, el HMI/`dnp3-operador`
  pueden mandar cualquier `DIRECT_OPERATE` sin credenciales -- y ademas,
  el outstation acepta varias conexiones simultaneas sin verificar cual
  es "el" master legitimo (ver la seccion 5 de `PROTOCOLO-DNP3.md`).
- **Unsolicited como canal de exfiltracion/DoS**: discutir que pasaria
  si un atacante inundara al master con `UNSOLICITED_RESPONSE` falsas
  (que este laboratorio no simula, pero que es un vector real en
  implementaciones DNP3 sin autenticacion).
- **Comparar con Modbus y OPC UA**: repetir el mismo ataque de
  manipulacion de setpoint (Laboratorio 3 de los tres protocolos) y
  comparar cuantos paquetes distintos hacen falta, y que tan facil es
  reconocer cada uno en un pcap.
- **Deteccion**: Wireshark/Zeek tienen analizadores DNP3 nativos; discutir
  que reglas de IDS podrian escribirse para alertar sobre
  `DIRECT_OPERATE` fuera de horario, o sobre `UNSOLICITED_RESPONSE` con
  una frecuencia anormal (indicio de un outstation comprometido "hablando
  de mas").
