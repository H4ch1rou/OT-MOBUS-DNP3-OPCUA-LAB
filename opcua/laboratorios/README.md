# Laboratorios de alumno - OPC UA (Central de Riego)

Tres guias practicas para resolver analizando una captura de trafico
(`.pcap`) que generas al interactuar con el dashboard web. Todo lo que se
pregunta debe poder justificarse con evidencia del pcap (numero de
paquete, Service, NodeId/BrowseName, valor).

Si no has hecho los laboratorios de [Modbus](../../modbus/laboratorios/README.md)
y [DNP3](../../dnp3/laboratorios/README.md) todavia, vale la pena
hacerlos primero: estas guias asumen que ya sabes leer una captura de
trafico OT basica y se enfocan en lo que es **distinto** en OPC UA.

| # | Laboratorio | Tema |
|---|-------------|------|
| 1 | [`lab-1-subscriptions.md`](lab-1-subscriptions.md) | Conexion/Browse inicial, y las Subscriptions nativas de OPC UA (avisos push) |
| 2 | [`lab-2-escritura-directa-variables.md`](lab-2-escritura-directa-variables.md) | Escritura directa de variables (sin objeto de comando); falta de autenticacion |
| 3 | [`lab-3-manipulacion-setpoints.md`](lab-3-manipulacion-setpoints.md) | Ataque de manipulacion de setpoint y su efecto en la Subscription |

## Antes de empezar (comun a los tres)

```bash
docker compose up -d --build
```

(desde la **raiz** del repositorio, no desde esta carpeta -- ver
[`README.md`](../README.md) del laboratorio si no lo tienes levantado, y
[`PROTOCOLO-OPCUA.md`](../PROTOCOLO-OPCUA.md) como referencia del
protocolo mientras analizas cada pcap).

Cada laboratorio pide generar un pcap **separado y con nombre propio**:

```bash
docker exec -it opcua-sniffer sh
tcpdump -i any -n -w /captures/lab1.pcap 'tcp port 4840'
# ... hacer la secuencia de pasos del laboratorio ...
# Ctrl+C para detener antes de pasar al siguiente laboratorio
```

## Que entregar

Para cada laboratorio: el `.pcap` correspondiente + un informe con las
respuestas, citando siempre evidencia concreta (numero de paquete,
Service, variable/NodeId, valor). Una respuesta sin evidencia del pcap no
se considera valida.
