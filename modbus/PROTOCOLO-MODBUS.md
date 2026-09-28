# Protocolo Modbus TCP - Guia de referencia y analisis de capturas

> Complemento de [`README.md`](README.md) (como levantar el laboratorio) y
> del [indice general](../README.md) de protocolos. Este documento explica
> el protocolo en si y da un paso a paso para leer `captures/modbus.pcap`
> en Wireshark y verificar, paquete a paquete, que cada accion del HMI
> realmente viajo por la red tal como se espera.

## 1. Que es Modbus

Modbus es un protocolo de comunicacion industrial creado por Modicon en
1979 para sus PLC. Es, por lejos, el protocolo OT/ICS mas usado en el
mundo, principalmente porque es simple, abierto y liviano -- y esa misma
simplicidad es la razon por la que **no tiene autenticacion, ni cifrado,
ni control de acceso de ningun tipo**. Casi todos los hallazgos de
seguridad de este laboratorio se explican con esa unica frase.

Puntos clave del modelo:

- **Cliente/servidor (tradicionalmente "maestro/esclavo")**: el cliente
  (en este lab, `modbus-master`, `webhmi` y `operador`) siempre inicia la
  conversacion. El servidor (`modbus-slave`, el RTU) nunca habla si no le
  preguntan; solo responde a lo que le piden.
- **Variantes de transporte**: Modbus RTU/ASCII corre sobre enlaces
  seriales (RS-232/RS-485); Modbus TCP corre sobre Ethernet/IP, puerto
  TCP **502**, que es el que usa este laboratorio.
- **Sin sesiones**: cada peticion es independiente. El servidor no sabe
  ni le importa quien le escribio la ultima vez -- por eso, en este
  laboratorio, tuvimos que inventar nosotros mismos una coil de "modo
  manual" para simular el equivalente a un selector local/remoto de un
  PLC real (ver la seccion correspondiente en `README.md`).

## 2. Estructura de un mensaje Modbus TCP

Un mensaje Modbus TCP (ADU, *Application Data Unit*) tiene dos partes:

```
[ MBAP Header (7 bytes) ][ PDU: Function Code (1 byte) + Data ]
```

**MBAP Header** (identifica y enruta el mensaje, es exclusivo de Modbus
sobre TCP; no existe en Modbus serial):

| Campo                | Tamaño | Descripcion                                   |
|-----------------------|--------|------------------------------------------------|
| Transaction Identifier | 2 bytes | Lo pone el cliente para emparejar pregunta/respuesta |
| Protocol Identifier    | 2 bytes | Siempre `0x0000` para Modbus                  |
| Length                 | 2 bytes | Bytes que siguen (Unit ID + PDU)               |
| Unit Identifier        | 1 byte  | Direccion del esclavo (en este lab, siempre 1) |

**PDU**: el primer byte es el **function code**; el resto son los datos
(direccion, cantidad, valores) segun esa funcion.

### Function codes usados en este laboratorio

| Codigo | Nombre                  | Uso en este lab                                         |
|--------|--------------------------|----------------------------------------------------------|
| `0x01` | Read Coils               | Leer estado de valvulas y modo manual/automatico          |
| `0x02` | Read Discrete Inputs     | Leer alarmas (humedad baja / encharcamiento)              |
| `0x03` | Read Holding Registers   | Leer humedad, caudal, umbrales                            |
| `0x05` | Write Single Coil        | Forzar una valvula, o cambiar el modo manual/automatico   |
| `0x06` | Write Single Register    | Cambiar un umbral (minimo o maximo)                        |

En una escritura de coil (FC 05), el valor va codificado como
`0xFF00` = **ON/true** o `0x0000` = **OFF/false** (Wireshark ya lo
interpreta y te muestra directamente `TRUE`/`FALSE`).

### Direccionamiento

Las direcciones que aparecen en el pcap son **crudas, base 0** (direccion
0 = primer registro/coil), que es como este laboratorio las define y
las que se usan en el codigo (`slave.py`, `master.py`, `app.py`). Si
alguna vez usas una herramienta que muestra direcciones "estilo Modicon"
(40001, 40002, ... para holding registers), esas son la misma direccion
0-based **mas 40001**; no la necesitas para este laboratorio, pero es
bueno saber que existe para no confundirte si la ves en otra parte.

## 3. Mapa de registros de este laboratorio

(copiado de `README.md` para tenerlo a mano mientras analizas el pcap)

Cada zona `z` (0..3 a nivel de protocolo = zona 1..4 en el HMI) usa:

```
base_hr = z * 10      # holding registers
base_di = z * 2       # discrete inputs
coil_valvula   = z
coil_modo      = 4 + z
```

| Tipo               | Direccion                | Descripcion                              |
|---------------------|---------------------------|---------------------------------------------|
| Holding Register    | `base_hr + 0`             | Humedad del suelo (%)                       |
| Holding Register    | `base_hr + 1`             | Caudal instantaneo (L/min)                  |
| Holding Register    | `base_hr + 2`             | Umbral MINIMO (abre valvula)                |
| Holding Register    | `base_hr + 3`             | Umbral MAXIMO (cierra valvula)              |
| Coil                | `z`                       | Electrovalvula de la zona                   |
| Coil                | `4 + z`                   | Modo manual (1) / automatico (0)            |
| Discrete Input      | `base_di + 0`             | Alarma humedad critica baja                 |
| Discrete Input      | `base_di + 1`             | Alarma encharcamiento                       |

Ejemplo: todo lo de la Zona 3 (`z=2`) vive en HR20-23, coil 2 (valvula),
coil 6 (modo), DI4-5.

## 4. Abrir y filtrar `captures/modbus.pcap` en Wireshark

1. Copia el archivo desde el servidor a tu maquina con Wireshark, por
   ejemplo: `scp usuario@servidor:~/.../modbus/captures/modbus.pcap .`
2. Abrelo con Wireshark. Al usar el puerto TCP 502, Wireshark reconoce y
   decodifica Modbus automaticamente (columna *Protocol* dira `Modbus/TCP`).
3. Filtro de pantalla recomendado: `modbus` (o `tcp.port == 502` si por
   algun motivo no aparece decodificado).
4. En la columna *Info* ya veras directamente algo como:
   `Query: Trans: 14; Unit: 1, Func: 5: Write Single Coil` seguido, en el
   siguiente paquete, de la respuesta (`Response: Trans: 14; ...`).
5. Click derecho sobre un paquete -> **Follow > TCP Stream** para ver toda
   la conversacion de esa conexion en un solo lugar (util para diferenciar
   la conexion de `modbus-master` de la de `webhmi`, ver seccion 6).

## 5. Paso a paso: que deberia verse para cada accion

Con el sniffer activo (`docker exec -it modbus-sniffer sh` y luego
`tcpdump -i any -n -w /captures/modbus.pcap 'tcp port 502'`, ver
`README.md`), reproduce estas acciones desde `http://localhost:9090` una
por una, y confirma en el pcap lo que corresponde:

| # | Accion en el HMI                                   | Paquetes esperados en el pcap                                                                 |
|---|-----------------------------------------------------|--------------------------------------------------------------------------------------------------|
| 1 | (nada, solo dejar correr) -- polling del SCADA       | Cada ~2s, en bloque: `FC03` sobre `base_hr..base_hr+3` y `FC02` sobre `base_di..base_di+1` por cada zona, mas un `FC01` sobre direccion `0`, cantidad `8` (lee las 8 coils de un tiro) |
| 2 | Click **"Abrir"** en una zona (ej. Zona 2, `z=1`)    | Dos escrituras `FC05` seguidas: primero direccion `5` (`4+1`, modo manual) valor `TRUE`/`0xFF00`; luego direccion `1` (coil valvula) valor `TRUE`/`0xFF00` |
| 3 | Click **"Cerrar"** en una zona                       | Igual que (2) pero el segundo paquete con la valvula en `FALSE`/`0x0000` |
| 4 | Click **"Volver a Automatico"**                      | Un solo `FC05` sobre la coil de modo (`4+z`) con valor `FALSE`/`0x0000` |
| 5 | Cambiar **umbral minimo** de una zona                | `FC06` Write Single Register sobre `base_hr+2`, con el valor nuevo en el campo *Data* |
| 6 | Cambiar **umbral maximo** de una zona                | `FC06` Write Single Register sobre `base_hr+3` |
| 7 | Una zona quedo en modo manual (paso 2) y pasa el tiempo | El polling del SCADA (fila 1) **sigue leyendo** esa zona normalmente, pero ya **no vuelve a aparecer** ningun `FC05` sobre la coil `z` de esa zona mientras siga en modo manual -- esa es la prueba de que el SCADA dejo de pelear por la valvula |

Truco para encontrar rapido las escrituras en medio de todo el polling:
usa el filtro `modbus.func_code == 5` (para coils) o
`modbus.func_code == 6` (para registros) en vez de mirar linea por linea.

## 6. Como diferenciar QUIEN escribio (SCADA vs HMI vs operador)

El protocolo Modbus en si **no lleva ninguna identidad de quien envia
cada mensaje** -- ese es justamente uno de los puntos de discusion de
este laboratorio. Pero como estamos capturando a nivel TCP/IP, Wireshark
si puede mostrarte el origen de cada conexion:

- **Statistics > Conversations > TCP** te lista cada conexion TCP por
  separado (IP:puerto origen -> IP:puerto destino). `modbus-master`,
  `webhmi` y `operador` abren cada uno su propia conexion persistente
  hacia `modbus-slave:502`, asi que cada fila de esa tabla es,
  practicamente, "una maquina distinta hablandole al RTU".
- Selecciona una conexion y **Follow > TCP Stream** para ver solo esos
  paquetes.
- Este truco funciona porque en este laboratorio cada componente vive en
  su propio contenedor con su propia IP. En una red OT real, con varios
  clientes SCADA/HMI compartiendo el mismo segmento, seguir "quien
  escribio que" es mucho mas dificil, y es exactamente el tipo de vacio
  que Modbus no resuelve por si solo (de ahi la necesidad de
  segmentacion, listas de control de acceso, o protocolos mas nuevos con
  autenticacion, como Modbus/TCP Security sobre TLS).

## 7. Ejercicio sugerido de cierre

1. Con el sniffer capturando, entra a `http://localhost:9090` y fuerza la
   apertura de la Zona 3.
2. En el pcap, filtra `modbus.func_code == 5` y ubica los dos paquetes
   que generaste (deberian tener el mismo `Transaction ID` consecutivo, uno
   inmediatamente despues del otro).
3. Anota la direccion decimal de cada uno y, usando la tabla de la
   seccion 3, confirma que corresponden a la coil de modo (`4+2=6`) y a
   la coil de valvula (`2`) de la Zona 3.
4. Revisa `docker compose logs modbus-master` y confirma que, desde ese
   momento, sus lineas para la Zona 3 dicen `modo=MANUAL (SCADA no
   interviene)` y que no vuelve a aparecer ningun `FC05` de esa coil en el
   pcap mientras eso dure.
5. Vuelve a poner la Zona 3 en automatico desde el HMI y repite el
   filtro: deberias ver un unico `FC05` nuevo sobre la coil `6`, y que el
   master retoma sus propias escrituras sobre la coil `2` en su siguiente
   ciclo.
