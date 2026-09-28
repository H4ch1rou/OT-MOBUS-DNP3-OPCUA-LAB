# Laboratorios de alumno - DNP3 (Central de Riego)

Tres guias practicas para resolver analizando una captura de trafico
(`.pcap`) que generas al interactuar con el dashboard web. Todo lo que se
pregunta debe poder justificarse con evidencia del pcap (numero de
paquete, function code, grupo/variacion/indice del objeto, valor).

Si no has hecho los [laboratorios de Modbus](../../modbus/laboratorios/README.md)
todavia, vale la pena hacerlos primero: estas guias asumen que ya sabes
leer una captura de trafico OT basica y se enfocan en lo que es
**distinto** en DNP3.

| # | Laboratorio | Tema |
|---|-------------|------|
| 1 | [`lab-1-integrity-poll-unsolicited.md`](lab-1-integrity-poll-unsolicited.md) | Estructura de 3 capas de DNP3, integrity poll, y la gran diferencia: unsolicited responses |
| 2 | [`lab-2-control-direct-operate.md`](lab-2-control-direct-operate.md) | Control de actuadores con DIRECT_OPERATE (CROB / Analog Output); falta de autenticacion |
| 3 | [`lab-3-manipulacion-setpoints.md`](lab-3-manipulacion-setpoints.md) | Ataque de manipulacion de setpoint y como se ve al forzar una UNSOLICITED_RESPONSE |

## Antes de empezar (comun a los tres)

```bash
cd dnp3
docker compose up -d --build
```

Ver [`README.md`](../README.md) si no lo tienes levantado, y
[`PROTOCOLO-DNP3.md`](../PROTOCOLO-DNP3.md) como referencia del protocolo
y del mapa de objetos mientras analizas cada pcap.

Cada laboratorio pide generar un pcap **separado y con nombre propio**:

```bash
docker exec -it dnp3-sniffer sh
tcpdump -i any -n -w /captures/lab1.pcap 'tcp port 20000'
# ... hacer la secuencia de pasos del laboratorio ...
# Ctrl+C para detener antes de pasar al siguiente laboratorio
```

## Que entregar

Para cada laboratorio: el `.pcap` correspondiente + un informe con las
respuestas, citando siempre evidencia concreta (numero de paquete,
function code, grupo/variacion, indice, valor). Una respuesta sin
evidencia del pcap no se considera valida.
