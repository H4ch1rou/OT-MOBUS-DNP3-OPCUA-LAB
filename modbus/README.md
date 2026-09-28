# PoC Modbus TCP - Central de Riego (Laboratorio OT)

Laboratorio Docker para practicar seguridad OT sobre Modbus TCP usando un
caso de uso real: una **central de riego con 4 zonas independientes**,
cada una con su propio sensor de humedad y su propia electrovalvula. Un
RTU de campo (esclavo) expone el proceso, una central SCADA (maestro) lo
controla automaticamente, y un **dashboard web tipo SCADA empresarial**
permite a los alumnos intervenir cada zona desde el navegador mientras
observan el efecto en la red con `tcpdump`.

> Este directorio es el laboratorio **Modbus** dentro del repositorio de
> protocolos OT. Ver el [indice general](../README.md) para otros
> protocolos (incluidos [DNP3](../dnp3/README.md) y [OPC UA](../opcua/README.md),
> que usan el mismo escenario de riego), [`PROTOCOLO-MODBUS.md`](PROTOCOLO-MODBUS.md)
> para una explicacion del protocolo en si y una guia paso a paso de como
> leer `modbus/captures/modbus.pcap` en Wireshark, y
> [`laboratorios/`](laboratorios/README.md) para tres guias de laboratorio
> que los alumnos resuelven analizando un pcap generado por ellos mismos.

## Componentes

Estos servicios se levantan junto con los de DNP3 y OPC UA desde el
**`docker-compose.yml` de la raiz del repositorio** (ya no hay un compose
por protocolo -- ver el [README raiz](../README.md)).

| Servicio          | Rol                                                         | Hostname interno   |
|--------------------|--------------------------------------------------------------|---------------------|
| `modbus-slave`     | RTU de campo: 4 zonas, cada una con sensor de humedad + electrovalvula | `modbus-slave`  |
| `modbus-master`    | Central SCADA (logica de control automatica, por zona)        | `modbus-master`     |
| `modbus-operador`  | Consola de operador en terminal, por zona (alternativa al dashboard, a demanda) | `modbus-operador` |
| `modbus-sniffer`   | Punto de captura (`tcpdump`), inactivo hasta que el alumno lo activa | -            |

El **dashboard web** de este laboratorio vive en el sitio unificado:
`http://localhost:9090/modbus/` (ver la seccion siguiente).

Todos comparten la red `ot_network` (compartida por los tres protocolos y
el dashboard), aislada del resto del host salvo por los puertos
publicados. Los contenedores se referencian siempre por nombre de host,
nunca por IP fija.

## Zonas de riego simuladas

| Zona | Nombre               |
|------|----------------------|
| 1    | Parronal             |
| 2    | Hortalizas           |
| 3    | Frutales             |
| 4    | Vivero               |

Cada zona tiene su propio sensor de humedad, caudal, umbrales de control
y electrovalvula -- independientes de las demas zonas.

## Mapa de registros del RTU (`modbus-slave`)

Cada zona `z` (z = 0..3 a nivel de protocolo; en el HMI/operador se
muestra como zona 1..4) reserva **10 holding registers** consecutivos y
**2 discrete inputs** consecutivos, con direccion base:

```
base_hr = z * 10
base_di = z * 2
coil    = z
```

| Tipo               | Direccion (relativa a la base) | Descripcion                       | Quien escribe             |
|---------------------|--------------------------------|-------------------------------------|---------------------------|
| Holding Register    | base_hr + 0                    | Humedad del suelo actual (%)       | proceso simulado           |
| Holding Register    | base_hr + 1                    | Caudal instantaneo (L/min)         | proceso simulado           |
| Holding Register    | base_hr + 2                    | Umbral MINIMO (abre valvula)       | SCADA / webhmi / operador  |
| Holding Register    | base_hr + 3                    | Umbral MAXIMO (cierra valvula)     | SCADA / webhmi / operador  |
| Coil                | `z`                             | Electrovalvula de la zona           | SCADA (si modo=automatico) / webhmi / operador |
| Coil                | `4 + z`                         | Modo MANUAL de la zona (1=manual, 0=automatico) | webhmi / operador |
| Discrete Input      | base_di + 0                    | Alarma de humedad critica baja (<10%) | proceso simulado        |
| Discrete Input      | base_di + 1                    | Alarma de encharcamiento (>95%)    | proceso simulado           |

Ejemplo concreto para la Zona 2 (`z=1`): humedad en HR10, caudal en HR11,
umbral minimo en HR12, umbral maximo en HR13, valvula en la coil 1, modo
manual en la coil 5, alarmas en DI2/DI3.

El master **lee** los umbrales en cada ciclo (no estan fijos en su
codigo), por lo que cualquier cambio hecho desde el HMI web, la consola
de operador, o por alguien no autorizado escribiendo directamente al RTU,
se refleja de inmediato en el comportamiento real de la valvula de esa
zona.

### Modo Manual vs. Automatico (por que la valvula "se cierra sola")

El RTU es I/O tonta: obedece la ultima escritura que reciba en la coil de
la valvula, venga de quien venga. Si nada mas existiera, el problema es
que **dos procesos compiten por la misma coil**: el lazo de histeresis
del SCADA (que revisa y reescribe cada `POLL_SECONDS`, por defecto 2s) y
la accion manual de un alumno desde `webhmi`/`operador`. Sin arbitraje,
el SCADA "gana" en su siguiente ciclo y deshace el cambio manual -- por
eso una valvula abierta a mano parecia cerrarse sola a los pocos
segundos.

Para evitarlo, cada zona tiene una coil extra de **modo manual**:

- En **modo automatico** (por defecto), `modbus-master` calcula y escribe
  el estado de la valvula segun humedad y umbrales, cada ciclo.
- En **modo manual**, `modbus-master` **no toca** esa coil: queda
  enteramente en manos de quien la escribio (HMI web u operador).

Desde `webhmi`, los botones "Abrir"/"Cerrar" activan el modo manual
automaticamente (para que el cambio quede firme), y el boton "Volver a
Automatico" devuelve el control al SCADA. Desde `operador`, las opciones
4/5 hacen lo mismo, y la opcion 6 devuelve la zona a automatico.

Este mismo mecanismo es, ademas, un buen tema de discusion: es el
equivalente simplificado del selector local/remoto que traen los PLC
reales, y muestra que sin una bandera explicita de este tipo, dos
escritores Modbus sobre el mismo punto simplemente se pisan -- el
protocolo no arbitra nada por si solo.

## Levantar el laboratorio

Desde la **raiz del repositorio** (no desde esta carpeta):

```bash
docker compose up -d --build
```

El `-d` (detached) es importante: todos los servicios quedan corriendo en
segundo plano de forma transparente, sin necesitar ninguna terminal
abierta. Esto levanta los tres protocolos a la vez (Modbus, DNP3, OPC UA)
mas el dashboard web unificado; `modbus-sniffer` arranca pero se queda
**inactivo**, sin capturar nada, hasta que un alumno entra a activarlo
(ver mas abajo).

Si en algun momento quieres revisar que esta pasando en algun servicio,
sin quedarte pegado a la terminal:

```bash
docker compose logs modbus-master   # ver que hizo el SCADA hasta ahora
docker compose ps                   # ver que esta corriendo
```

Abre en el navegador:

```
http://localhost:9090/modbus/
```

El dashboard muestra un resumen general (valvulas abiertas, caudal total,
humedad promedio, alarmas activas), un esquema de la red de riego con las
4 zonas y sus valvulas, y una tarjeta detallada por zona donde los
alumnos pueden:

- **Abrir / Cerrar** la valvula de esa zona (pasa la zona a modo MANUAL
  automaticamente, para que el cambio no sea sobreescrito por el SCADA).
- **Volver a Automatico**: devuelve el control de la valvula al SCADA.
- Cambiar su **umbral minimo** y **umbral maximo** de humedad.

El **menu lateral** (presente en todo el sitio, no solo en este
dashboard) da acceso directo a toda la documentacion: este README,
`PROTOCOLO-MODBUS.md`, el indice de protocolos, las tres guias de
`laboratorios/`, la pauta de correccion (bajo "Solucionario 🔒", detras de
un login docente -- ver el [README raiz](../README.md#acceso-docente--solucionario)),
y ademas a los dashboards/documentacion de DNP3 y OPC UA sin salir del
sitio. Los `.md` se montan de solo lectura en el contenedor `webhmi`, asi
que cualquier edicion a estos archivos se ve reflejada en la web sin
reconstruir la imagen.

Cada boton hace una llamada al backend Flask, que traduce la accion en
una escritura Modbus TCP real (FC 05 "Write Single Coil" o FC 06 "Write
Single Register") hacia el RTU, sobre la coil/registros de esa zona
especifica. No hay ninguna autenticacion: es a proposito, para poder
discutirlo despues en clase. Ver la seccion "Modo Manual vs. Automatico"
mas arriba para el detalle de por que existe este boton.

`modbus-operador` (consola de texto, alternativa al dashboard, tambien
por zona) **no** arranca con `up` porque es interactiva. Se invoca a
demanda:

```bash
docker compose run --rm modbus-operador
```

## Activar el sniffing (a mano, desde dentro del contenedor)

El contenedor `sniffer` comparte el namespace de red del RTU
(`network_mode: service:modbus-slave`), asi que ve exactamente el mismo
trafico que le llega al equipo de campo: polling del SCADA y cualquier
escritura hecha desde `webhmi` u `operador`, para cualquiera de las 4
zonas. Pero **no captura nada por si solo**: arranca inactivo a proposito,
para que sea el alumno quien entre y decida cuando empezar a escuchar la
red (como lo haria alguien con acceso fisico/logico al segmento OT).

Para entrar al contenedor:

```bash
docker exec -it modbus-sniffer sh
```

Una vez dentro, para ver el trafico en vivo (hex + ASCII):

```bash
tcpdump -i any -n -A 'tcp port 502'
```

O, si ademas quieres guardar la captura para analizarla despues con
Wireshark (queda en el host, en `modbus/captures/modbus.pcap`):

```bash
tcpdump -i any -n -w /captures/modbus.pcap 'tcp port 502'
```

Ese comando queda "enganchado" a la terminal mientras esta activo (es la
unica consola que el alumno debe mantener abierta a proposito, porque es
la que esta usando para sniffear). Para salir, `Ctrl+C` y luego `exit`.

### Flujo de trabajo sugerido para la clase

1. `docker compose up -d --build` (desde la raiz del repositorio; todo
   corre en segundo plano, sin consolas abiertas).
2. Abrir `http://localhost:9090/modbus/` en el navegador.
3. En otra terminal, entrar al sniffer y lanzar tcpdump (pasos de arriba).
4. En la pagina web, elegir una zona (por ejemplo "Zona 3 - Frutales"),
   cambiar su umbral minimo o presionar "Abrir"/"Cerrar".
5. Ver en la terminal del sniffer como aparece de inmediato un paquete
   nuevo con funcion 0x06 (Write Single Register) o 0x05 (Write Single
   Coil), con la direccion (que identifica la zona) y el valor nuevo
   visibles en hexadecimal/ASCII.
6. Revisar `docker compose logs modbus-master` y confirmar que el lazo de
   control de esa zona reacciono al cambio.
7. Abrir `modbus/captures/modbus.pcap` con Wireshark (filtro `modbus` o
   `tcp.port == 502`) y comparar, paquete a paquete, con las acciones
   hechas en el HMI, identificando a que zona corresponde cada escritura
   segun la direccion del registro/coil.

Para el detalle de que function code y direccion exacta esperar para cada
accion (abrir valvula, cambiar umbral, volver a automatico, etc.), ver la
guia [`PROTOCOLO-MODBUS.md`](PROTOCOLO-MODBUS.md).

Detener y limpiar:

```bash
docker compose down
```

## Ideas para extender el laboratorio

- **Falta de autenticacion**: mostrar que `webhmi`/`operador` pueden
  escribir cualquier umbral o coil, de cualquier zona, sin ninguna
  credencial ni validacion de origen -- cualquiera con acceso a
  `ot_network` puede alterar el riego de todo el predio.
- **Ataque de manipulacion de setpoint**: desde el HMI, fijar el umbral
  maximo de una zona muy bajo para forzar cierres de valvula constantes
  (denegacion de riego en esa zona), y verlo tanto en el pcap como en el
  comportamiento del proceso simulado.
- **Comparar HMI legitimo vs. escritura directa**: hacer que un grupo use
  `webhmi` normalmente y otro grupo escriba directo al RTU con
  `docker compose run --rm modbus-operador` (o con `pymodbus.console` desde otro
  contenedor), y comparar en el pcap si se puede distinguir el origen
  "autorizado" del "no autorizado" -- spoiler: a nivel de protocolo, no.
- **Correlacionar direccion -> zona**: como ejercicio, pedir a los
  alumnos que, mirando solo el pcap (sin ver el HMI), deduzcan a que zona
  y a que variable corresponde cada escritura, usando el mapa de
  registros de este README.
- **Deteccion**: alimentar `modbus/captures/modbus.pcap` a un IDS con reglas
  Modbus (Suricata) o al analizador `modbus` de Zeek para generar alertas
  ante escrituras fuera de un rango esperado, o sobre zonas especificas.
- **Segmentacion**: mover `webhmi`/`operador` a una red separada y forzar
  que solo puedan llegar al RTU pasando por `modbus-master` (una especie
  de DMZ IT/OT), para comparar el trafico legitimo contra el directo.
