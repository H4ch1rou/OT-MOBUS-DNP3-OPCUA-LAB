# Laboratorios de alumno - Modbus TCP (Central de Riego)

Tres guias practicas para resolver analizando una captura de trafico
(`.pcap`) que tu mismo generas al interactuar con el dashboard web. No se
responde mirando el codigo fuente: todo lo que se pregunta debe poder
justificarse con evidencia del pcap (numero de paquete, Transaction ID,
direccion, valor hexadecimal, etc.).

| # | Laboratorio | Tema |
|---|-------------|------|
| 1 | [`lab-1-reconocimiento-pasivo.md`](lab-1-reconocimiento-pasivo.md) | Estructura de Modbus TCP y polling automatico (sin interactuar con el HMI) |
| 2 | [`lab-2-escritura-actuadores.md`](lab-2-escritura-actuadores.md) | Escritura de actuadores sin autenticacion; modo manual vs automatico |
| 3 | [`lab-3-manipulacion-setpoints.md`](lab-3-manipulacion-setpoints.md) | Ataque de manipulacion de setpoint y deteccion |

## Antes de empezar (comun a los tres)

Necesitas el laboratorio Modbus corriendo y el sniffer activado. Ver el
[`README.md`](../README.md) principal si no lo tienes levantado, y
[`PROTOCOLO-MODBUS.md`](../PROTOCOLO-MODBUS.md) como referencia del
protocolo y del mapa de registros mientras analizas cada pcap.

```bash
cd modbus
docker compose up -d --build
```

Cada laboratorio pide generar un pcap **separado y con nombre propio**
(`lab1.pcap`, `lab2.pcap`, `lab3.pcap`) para que tu entrega quede
acotada al ejercicio correspondiente, en vez de una captura larga y
mezclada. Para eso, cada vez que actives el sniffer usa un nombre de
archivo distinto:

```bash
docker exec -it modbus-sniffer sh
tcpdump -i any -n -w /captures/lab1.pcap 'tcp port 502'
# ... hacer la secuencia de pasos del laboratorio ...
# Ctrl+C para detener la captura antes de pasar al siguiente laboratorio
```

Los archivos quedan en `./captures/` en el host (fuera del contenedor),
listos para copiarlos a tu maquina y abrirlos con Wireshark.

## Que entregar

Para cada laboratorio: el archivo `.pcap` correspondiente + un informe
corto con las respuestas a las preguntas, citando siempre la evidencia
concreta que usaste (numero de paquete, Transaction ID, direccion en
decimal, valor en hexadecimal). Una respuesta sin evidencia del pcap no
se considera valida, aunque sea correcta.

## Recomendacion de orden

Los tres laboratorios estan pensados para hacerse en orden (1 -> 2 -> 3):
el Laboratorio 1 te familiariza con leer un pcap de Modbus sin tener que
identificar todavia nada "raro"; el Laboratorio 2 introduce escrituras y
el mecanismo de modo manual/automatico; el Laboratorio 3 usa todo lo
anterior para razonar sobre un ataque real y su deteccion.
