# Protocolo DNP3 - Guia de referencia y analisis de capturas

> Complemento de [`README.md`](README.md) (como levantar el laboratorio) y
> del [indice general](../README.md) de protocolos. Si no has visto el
> laboratorio Modbus todavia, vale la pena hacerlo primero: este
> documento asume que conoces esos conceptos basicos y se enfoca en las
> diferencias.

## 1. Que es DNP3

DNP3 (Distributed Network Protocol, version 3) nacio a comienzos de los
90 pensado especificamente para el sector electrico (subestaciones,
distribucion), y hoy tambien se usa en agua/saneamiento y otras
utilities. A diferencia de Modbus (disenado originalmente para
automatizacion de planta, punto a punto y muy simple), DNP3 se diseno
desde el principio para redes SCADA mas grandes y con enlaces menos
confiables (radio, lineas seriales largas), lo que se nota en su
arquitectura de tres capas y en mecanismos como la confirmacion de
aplicacion. Esta estandarizado internacionalmente como **IEEE 1815**.

Igual que Modbus, sigue un modelo **maestro/esclavo** -- aqui llamado
**master/outstation** -- pero con una diferencia arquitectonica central:

> **En Modbus, el esclavo NUNCA habla si el maestro no le pregunta
> primero. En DNP3, el outstation SI puede iniciar la comunicacion por su
> cuenta**, mandando una `UNSOLICITED_RESPONSE` cuando algo cambia (por
> ejemplo, una alarma), sin que el master la haya pedido.

Esa es la razon de ser del Laboratorio 1 de esta carpeta.

## 2. Arquitectura de capas (vs. Modbus)

Modbus tiene esencialmente una sola capa (ADU = MBAP Header + PDU). DNP3
define tres capas explicitas, cada una con su propio encabezado:

```
Capa de enlace     -> agrega direccionamiento de estacion y CRC por bloque
Capa de transporte -> permite partir un mensaje grande en varios "segmentos"
Capa de aplicacion -> function code + objetos de datos (lo mas parecido a un PDU Modbus)
```

### Capa de enlace (Data Link Layer)

```
[0x05][0x64][LENGTH][CONTROL][DEST lo][DEST hi][SRC lo][SRC hi][CRC lo][CRC hi]
  |______________________________________________________|
                 header (8 bytes) -> con su propio CRC-16

[bloque de datos de hasta 16 bytes][CRC-16 del bloque]
[bloque de datos de hasta 16 bytes][CRC-16 del bloque]
...
```

- `0x05 0x64` son los "start bytes", fijos, identifican el inicio de una
  trama DNP3 (el equivalente a que Modbus TCP no necesite start bytes
  porque ya viaja dentro de un socket TCP dedicado).
- `CONTROL` indica direccion (quien envia: master u outstation) y el tipo
  de trama de enlace. En este laboratorio siempre usamos "Unconfirmed
  User Data": `0xC4` cuando el frame lo manda el master, `0x44` cuando lo
  manda el outstation.
- `DEST`/`SRC` son direcciones de **estacion** DNP3 (no direcciones IP):
  en este laboratorio, master = 1, outstation = 10.
- El **CRC no es uno solo por trama**: cada bloque de hasta 16 bytes de
  datos lleva su propio CRC-16 (variante "CRC-16/DNP"). Es una diferencia
  notoria frente a Modbus, que solo calcula un CRC/checksum una vez por
  mensaje completo (y en Modbus TCP ni siquiera eso, porque TCP ya
  garantiza integridad a nivel de transporte).

### Capa de transporte (Transport Layer)

Un solo byte de cabecera por cada trama de enlace:

```
bit 7 = FIN (es el ultimo segmento del mensaje)
bit 6 = FIR (es el primer segmento del mensaje)
bits 5-0 = numero de secuencia (0-63)
```

Sirve para partir mensajes de aplicacion grandes en varios segmentos (uno
por trama de enlace, maximo ~250 bytes de datos cada una). En este
laboratorio, todos los mensajes son pequenos y caben en un solo segmento
(`FIR=1, FIN=1`).

### Capa de aplicacion (Application Layer)

```
[CONTROL][FUNCTION CODE][IIN (solo en respuestas, 2 bytes)][objetos...]
```

`CONTROL` tiene esta forma (parecida a la de transporte, pero con mas
banderas):

```
bit 7 = FIR, bit 6 = FIN
bit 5 = CON (pide confirmacion de aplicacion)
bit 4 = UNS (este mensaje es una respuesta no solicitada, o su confirmacion)
bits 3-0 = numero de secuencia (0-15)
```

`IIN` (Internal Indications) son 2 bytes de banderas de estado del
outstation (reinicio, necesita hora, etc.) que solo van en las
respuestas. En este laboratorio siempre van en `0x0000` (simplificacion:
no implementamos esos escenarios).

## 3. Function codes usados en este laboratorio

| Codigo | Nombre                | Quien lo manda | Uso en este lab                                    |
|--------|------------------------|-----------------|------------------------------------------------------|
| `0x00` | CONFIRM                | Master          | Confirma haber recibido una UNSOLICITED_RESPONSE      |
| `0x01` | READ                   | Master          | Integrity poll: pide todos los puntos (Class 0)       |
| `0x05` | DIRECT_OPERATE         | Master          | Ordena una accion (abrir valvula, cambiar umbral)     |
| `0x81` | RESPONSE               | Outstation      | Responde a READ o a DIRECT_OPERATE                    |
| `0x82` | UNSOLICITED_RESPONSE   | Outstation      | Avisa un cambio (alarma) SIN que nadie se lo pida     |

## 4. Direccionamiento: por GRUPO, no un espacio plano

Esta es otra diferencia importante frente a Modbus. En Modbus hay 4
"tablas" (coils, discrete inputs, holding registers, input registers) y
dentro de cada una las direcciones son un espacio plano compartido por
todo el dispositivo. En DNP3, los datos se organizan por **grupo y
variacion** (el "tipo" de dato), y cada grupo tiene **su propio espacio
de indices independiente**, empezando en 0.

### Grupos de objetos usados en este laboratorio

Cada zona `z` (0..3 a nivel de protocolo = zona 1..4 en el HMI) usa
**2 indices** dentro de cada grupo:

```
indice = z * 2 + 0   ->  primera variable del grupo
indice = z * 2 + 1   ->  segunda variable del grupo
```

| Grupo / Variacion              | Tipo de dato                        | indice+0        | indice+1              |
|----------------------------------|--------------------------------------|------------------|------------------------|
| Group 30 Var 5 (Analog Input, float) | Sensor, solo lectura            | humedad (%)      | caudal (L/min)         |
| Group 40/41 Var 2 (Analog Output, 16-bit) | Setpoint, controlable        | umbral minimo    | umbral maximo          |
| Group 1 Var 2 (Binary Input, con flags) | Alarma, solo lectura           | humedad critica baja | encharcamiento     |
| Group 10/12 (Binary Output / CROB) | Actuador, controlable             | valvula          | modo manual/automatico |

Ejemplo concreto para la Zona 3 (`z=2`): humedad y caudal en Analog Input
indices 4 y 5; umbrales en Analog Output indices 4 y 5 (espacio
**separado** del de Analog Input, aunque el numero coincida); alarmas en
Binary Input indices 4 y 5; valvula y modo en Binary Output/CROB indices
4 y 5.

### Tabla de equivalencias Modbus <-> DNP3

| Concepto                          | Modbus                          | DNP3                                              |
|-------------------------------------|-----------------------------------|------------------------------------------------------|
| Sensor de solo lectura (numerico)   | Holding/Input Register (FC 03/04) | Analog Input -- Group 30                             |
| Alarma de solo lectura (booleana)   | Discrete Input (FC 02)            | Binary Input -- Group 1                              |
| Setpoint escribible (numerico)      | Holding Register (FC 06/16)       | Analog Output -- status Group 40, comando Group 41   |
| Actuador escribible (booleano)      | Coil (FC 05/15)                   | Binary Output status Group 10, control CROB Group 12 |
| "Dame todo"                         | Leer cada tabla por separado       | READ con Group 60 Var 1 (Class 0), qualifier "todos" |
| Iniciativa de la comunicacion       | Solo el master                    | Master, o el outstation via UNSOLICITED_RESPONSE      |

## 5. Simplificaciones de este laboratorio

Este laboratorio usa un codec DNP3 propio (`common/dnp3lib.py`), escrito
a mano porque no existe una libreria DNP3 pura en Python que sea liviana
y este mantenida (la unica completa, `pydnp3`, envuelve una libreria C++
que hay que compilar). El codec implementa el framing real (con CRC-16
verificado) y los function codes/grupos de arriba, pero deliberadamente
**no** implementa:

- Capa de enlace confirmada (siempre "Unconfirmed User Data").
- Fragmentacion multi-segmento (nuestros mensajes son chicos y caben en uno).
- Objetos de **evento** con marca de tiempo (Group 2, 32, etc.): la
  `UNSOLICITED_RESPONSE` de este laboratorio reenvia el valor **estatico**
  del punto que cambio, en vez de un evento temporal, para mantener el
  codec simple. El punto pedagogico central -- que el outstation puede
  iniciar la comunicacion -- se mantiene intacto.
- Secure Authentication (SAv5/SAv6): DNP3 "clasico" tampoco la trae por
  defecto, asi que esto refleja fielmente la inseguridad real del
  protocolo tal como se despliega en la mayoria de los sistemas, no es
  una simplificacion que esconda algo.
- Un solo master autorizado: un outstation DNP3 real normalmente esta
  configurado para aceptar solo a un master conocido. Este laboratorio
  acepta varias conexiones simultaneas a proposito (como el esclavo
  Modbus del otro laboratorio), para poder mostrar el mismo problema de
  fondo: nada impide que `webhmi`, `operador`, o un atacante, se
  conecten directo al puerto 20000 y manden comandos como si fueran el
  SCADA legitimo.

## 6. Abrir y filtrar `captures/dnp3.pcap` en Wireshark

1. Copia el archivo desde el servidor: `scp usuario@servidor:.../dnp3/captures/dnp3.pcap .`
2. Abrelo con Wireshark. Al usar el puerto TCP 20000 (el puerto estandar
   de DNP3), Wireshark lo decodifica automaticamente (columna *Protocol*
   dira `DNP 3.0`).
3. Filtro de pantalla recomendado: `dnp3`.
4. Filtros utiles:
   - `dnp3.al.func == 1` -> solo los READ (integrity polls) del master.
   - `dnp3.al.func == 5` -> solo los DIRECT_OPERATE (comandos).
   - `dnp3.al.func == 130` -> solo las UNSOLICITED_RESPONSE (0x82 = 130 decimal).
   - `dnp3.al.func == 0` -> solo los CONFIRM.
5. En el panel de detalle, Wireshark separa claramente las 3 capas:
   "Data Link Layer" (direcciones, control), "Transport Control", y
   "Application Layer" (function code, IIN, y cada "Object Header" con su
   grupo/variacion/calificador y los puntos que trae).

## 7. Paso a paso: que deberia verse para cada accion

| # | Accion en el HMI                                  | Paquetes esperados en el pcap                                                                 |
|---|------------------------------------------------------|----------------------------------------------------------------------------------------------|
| 1 | (nada, solo dejar correr) -- polling del SCADA         | Cada ~2s: un READ (func=1) con objeto Group 60 Var 1 qualifier "todos" (integrity poll), seguido de una RESPONSE (func=129) con varios object headers (Group 1, 10, 30, 40) |
| 2 | Click **"Abrir"** en una zona (ej. Zona 2, `z=1`)      | Dos DIRECT_OPERATE (func=5) con objeto Group 12 Var 1 (CROB): primero sobre el indice de modo (`4+1=5`... el indice DENTRO del grupo Binary Output/CROB es `z*2+1`), luego sobre el indice de valvula (`z*2+0`); cada uno con su RESPONSE (func=129) echando el CROB con status=0 (exito) |
| 3 | Click **"Cerrar"**                                    | Igual que (2), con el CROB de la valvula en OpType=LATCH_OFF (4) en vez de LATCH_ON (3) |
| 4 | Click **"Volver a Automatico"**                       | Un DIRECT_OPERATE sobre la coil de modo con OpType=LATCH_OFF |
| 5 | Cambiar **umbral minimo/maximo**                      | Un DIRECT_OPERATE (func=5) con objeto Group 41 Var 2 (Analog Output command), 16 bits, sobre el indice `z*2+0` (minimo) o `z*2+1` (maximo) |
| 6 | Una alarma cambia de estado (ej. Laboratorio 3)       | Una UNSOLICITED_RESPONSE (func=130) que el outstation manda **sin que nadie la pida**, con `CON=1` (pide confirmacion) y objeto Group 1 Var 2 (Binary Input); inmediatamente despues, un CONFIRM (func=0) del master con el mismo numero de secuencia |

## 8. Como reconocer una respuesta no solicitada en el pcap

Busca en Wireshark un paquete con `dnp3.al.func == 130`. A diferencia de
una RESPONSE normal (func=129), este:

- **No viene precedido** por un READ o DIRECT_OPERATE con el mismo numero
  de secuencia de aplicacion (revisa el campo `Application Control` ->
  `Sequence`): una RESPONSE normal siempre "hace eco" de la secuencia del
  pedido; una UNSOLICITED_RESPONSE usa su **propio contador independiente**
  de secuencias, que el outstation lleva por su cuenta.
- Tiene el bit `UNS` (Unsolicited) activado en el Application Control.
- Va seguida, uno o dos paquetes despues, de un `CONFIRM` (func=0) que
  tambien tiene el bit `UNS` activado y el mismo numero de secuencia --
  esa es la "conversacion completa" de un evento no solicitado.

Ese patron -- outstation habla primero, sin que nadie le haya preguntado
nada -- es imposible de generar en el laboratorio Modbus. Es la prueba
mas clara, mirando solo el pcap, de que estas frente a DNP3 y no Modbus.
