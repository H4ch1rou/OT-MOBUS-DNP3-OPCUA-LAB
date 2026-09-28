# Laboratorio 3 - Manipulacion de setpoints (ataque de integridad)

## Escenario

Igual que en los laboratorios Modbus y DNP3: actuas como alguien con
acceso a la red OT que quiere que la **Zona 4 - Vivero** deje de recibir
riego, sin tocar la valvula directamente, manipulando solo su umbral
minimo. La diferencia interesante en OPC UA: como el master esta
suscrito a las alarmas (Laboratorio 1), la propia alarma que provoca tu
ataque genera una notificacion `Publish` que el SCADA recibe de inmediato
-- sin tener que esperar su siguiente poll.

## Objetivos

- Ejecutar y documentar un ataque de manipulacion de setpoint via un
  `Write` directo sobre una variable Analog (`UmbralMinimo`).
- Medir el impacto en el proceso fisico simulado.
- Observar como la notificacion `Publish` generada por la propia alarma
  hace visible el ataque casi de inmediato.

## Procedimiento

1. Verifica que la Zona 4 este en modo Automatico. Anota desde el
   dashboard su humedad, umbral minimo y umbral maximo actuales, y si la
   valvula esta abierta o cerrada.
2. Arranca la captura:
   ```bash
   docker exec -it opcua-sniffer sh
   tcpdump -i any -n -w /captures/lab3.pcap 'tcp port 4840'
   ```
3. En `http://localhost:9090/opcua/`, cambia el **umbral minimo** de la
   Zona 4 a `0` y presiona "Aplicar".
4. Espera y observa la tarjeta de la Zona 4 (y/o
   `docker compose logs -f opcua-master`) durante al menos 30-40 segundos
   -- el tiempo suficiente para que, con el umbral en 0, la humedad baje
   lo bastante como para disparar la alarma de humedad critica baja.
5. Detén la captura (`Ctrl+C`).

## Preguntas

1. Antes del ataque, ¿la valvula de la Zona 4 estaba abierta o cerrada?
   Explica por que usando la logica de histeresis del master
   (`humedad <= umbral_min -> abre`).

2. Ubica el `Write` del paso 3. ¿Sobre que variable es
   (`Zona4/UmbralMinimo`)? ¿Que valor trae?

3. Con umbral minimo = 0, la condicion `humedad <= 0` recien se cumple
   cuando la humedad simulada llega **exactamente** a 0 (esta acotada
   entre 0 y 100). ¿Este ataque es una negacion de riego permanente, o
   solo un retraso? ¿Por que sigue siendo efectivo durante la ventana de
   este laboratorio aunque no sea permanente?

4. Busca en el pcap un mensaje `Publish` que haya aparecido DESPUES de tu
   `Write` del paso 3, sin que el cliente hubiera mandado ningun `Read` o
   `Write` justo antes. ¿Que `MonitoredItemNotification` trae, y confirma
   que corresponde a la alarma de humedad baja de la Zona 4?

5. Revisa `docker compose logs opcua-master` alrededor del momento en que
   aparecio ese `Publish`. ¿El master registro la alarma casi de
   inmediato, o tuvo que esperar a su siguiente ciclo de polling para
   enterarse? Justifica con las marcas de tiempo de los logs.

6. Comparando con Modbus (donde el master solo se entera de una alarma en
   su siguiente poll) y con DNP3 (que tambien avisa casi de inmediato via
   `UNSOLICITED_RESPONSE`): ¿en que se parecen y en que se diferencian el
   mecanismo de Subscription de OPC UA y el de DNP3, en terminos de qué
   tan rapido se entera el SCADA de un problema?

7. Contando paquetes en el pcap: ¿cuantos mensajes tuvo que mandar el
   atacante para lograr el efecto (un solo `Write`), versus cuantos
   genero el propio sistema como consecuencia (el `Publish` con la
   notificacion)? ¿Quien "delato" mas trafico al ataque: el atacante o el
   propio proceso fisico reaccionando?

8. Propon, en palabras, una condicion que un IDS podria usar para
   detectar este ataque basandose en el pcap -- por ejemplo, sobre el
   `Write` original (*"alertar si se escribe una variable
   `UmbralMinimo` con un valor por debajo de un piso razonable"*), o
   sobre el patron "notificacion `Publish` de una variable de alarma poco
   despues de un `Write` sobre una variable de umbral de la misma zona".

## Entregable

- `lab3.pcap`
- Informe con las 8 respuestas, incluyendo los valores de humedad/valvula
  anotados antes y despues del ataque, y evidencia de pcap (numero de
  paquete, Service, variable, valor) para las preguntas que la requieren.
