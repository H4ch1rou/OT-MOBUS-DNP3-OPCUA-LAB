# Laboratorio 3 - Manipulacion de setpoints (ataque de integridad)

## Escenario

Igual que en el laboratorio Modbus: actuas como alguien con acceso a la
red OT que quiere que la **Zona 4 - Vivero** deje de recibir riego, sin
tocar la valvula directamente, manipulando solo su umbral minimo. La
diferencia interesante en DNP3: como el outstation puede mandar
`UNSOLICITED_RESPONSE`, la propia alarma que provoca tu ataque puede
"delatarte" ante el SCADA sin que nadie tenga que preguntar -- algo que
en Modbus no pasa.

## Objetivos

- Ejecutar y documentar un ataque de manipulacion de setpoint via
  `DIRECT_OPERATE` sobre un Analog Output.
- Medir el impacto en el proceso fisico simulado.
- Observar como la `UNSOLICITED_RESPONSE` generada por la propia alarma
  hace visible el ataque, y discutir esa diferencia frente a Modbus.

## Procedimiento

1. Verifica que la Zona 4 este en modo Automatico. Anota desde el HMI su
   humedad, umbral minimo y umbral maximo actuales, y si la valvula esta
   abierta o cerrada.
2. Arranca la captura:
   ```bash
   docker exec -it dnp3-sniffer sh
   tcpdump -i any -n -w /captures/lab3.pcap 'tcp port 20000'
   ```
3. En el HMI, cambia el **umbral minimo** de la Zona 4 a `0` y presiona
   "Aplicar".
4. Espera y observa la tarjeta de la Zona 4 (y/o
   `docker compose logs -f dnp3-master`) durante al menos 30-40 segundos
   -- el tiempo suficiente para que, con el umbral en 0, la humedad baje
   lo bastante como para disparar la alarma de humedad critica baja.
5. Detén la captura (`Ctrl+C`).

## Preguntas

1. Antes del ataque, ¿la valvula de la Zona 4 estaba abierta o cerrada?
   Explica por que usando la logica de histeresis del master
   (`humedad <= umbral_min -> abre`).

2. Ubica el `DIRECT_OPERATE` (func=5) del paso 3. ¿Sobre que
   grupo/variacion y que indice es? Verifica que corresponde al umbral
   minimo de la Zona 4 (Analog Output command, Group 41).

3. Con umbral minimo = 0, la condicion `humedad <= 0` recien se cumple
   cuando la humedad simulada llega **exactamente** a 0 (esta acotada
   entre 0 y 100). ¿Este ataque es una negacion de riego permanente, o
   solo un retraso? ¿Por que sigue siendo efectivo durante la ventana de
   este laboratorio aunque no sea permanente?

4. Busca en el pcap una `UNSOLICITED_RESPONSE` (func=130) que haya
   aparecido DESPUES de tu `DIRECT_OPERATE` del paso 3, sin que nadie la
   pidiera. ¿Que objeto trae, y confirma que corresponde a la alarma de
   humedad baja de la Zona 4?

5. Revisa `docker compose logs dnp3-master` alrededor del momento en que
   aparecio esa UNSOLICITED_RESPONSE. ¿El master registro la alarma
   apenas la recibio, o tuvo que esperar a su siguiente integrity poll
   para enterarse? Justifica con las marcas de tiempo de los logs.

6. Comparando con el Laboratorio 3 de Modbus (donde el master solo se
   entera de una alarma en su siguiente poll, cada `POLL_SECONDS`):
   ¿la respuesta no solicitada de DNP3 hace que este tipo de ataque sea
   MAS facil o MAS dificil de pasar desapercibido para el SCADA? Explica
   tu respuesta.

7. Contando paquetes en el pcap: ¿cuantos mensajes tuvo que mandar el
   atacante para lograr el efecto (un solo `DIRECT_OPERATE`), versus
   cuantos genero el propio sistema como consecuencia (la
   `UNSOLICITED_RESPONSE` y su `CONFIRM`)? ¿Quien "delato" mas trafico al
   ataque: el atacante o el propio proceso fisico reaccionando?

8. Propon, en palabras, una condicion que un IDS podria usar para
   detectar este ataque basandose en el pcap -- puedes proponerla sobre
   el `DIRECT_OPERATE` original (similar a la del laboratorio Modbus) O
   sobre el patron "UNSOLICITED_RESPONSE de alarma baja poco despues de
   un DIRECT_OPERATE sobre un umbral" (una correlacion de dos eventos,
   mas especifica).

## Entregable

- `lab3.pcap`
- Informe con las 8 respuestas, incluyendo los valores de humedad/valvula
  anotados antes y despues del ataque, y evidencia de pcap (numero de
  paquete, function code, indice, valor) para las preguntas que la
  requieren.
