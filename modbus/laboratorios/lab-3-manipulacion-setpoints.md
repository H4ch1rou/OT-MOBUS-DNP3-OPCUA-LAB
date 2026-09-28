# Laboratorio 3 - Manipulacion de setpoints (ataque de integridad)

## Escenario

Actúas como alguien con acceso a la red OT (por ejemplo, tras comprometer
una estacion de ingenieria) que quiere que la **Zona 4 - Vivero** deje de
recibir riego, pero sin tocar la valvula directamente -- eso seria muy
evidente y facil de detectar (ver Laboratorio 2). En vez de eso, vas a
manipular su **umbral minimo**, dejando que el propio SCADA "decida" no
regar nunca más.

## Objetivos

- Ejecutar y documentar un ataque simple de manipulacion de setpoint,
  similar a los ataques de integridad reportados en incidentes ICS reales.
- Medir el impacto en el proceso fisico simulado (humedad/valvula).
- Comparar, en trafico generado, este ataque contra forzar la valvula
  directamente, y proponer una forma de detectarlo.

## Procedimiento

1. Verifica que la **Zona 4** este en modo **Automatico** (si no, vuelve
   a ponerla con el boton correspondiente).
2. Anota desde el HMI: humedad actual, umbral minimo y umbral maximo de
   la Zona 4, y si su valvula esta abierta o cerrada.
3. Arranca la captura:
   ```bash
   docker exec -it modbus-sniffer sh
   tcpdump -i any -n -w /captures/lab3.pcap 'tcp port 502'
   ```
4. En el HMI, cambia el **umbral minimo** de la Zona 4 a `0` y presiona
   "Aplicar".
5. Espera al menos 15-20 segundos (varios ciclos de polling del SCADA,
   que corre cada `POLL_SECONDS`) observando la tarjeta de la Zona 4 y/o
   `docker compose logs -f modbus-master`.
6. Detén la captura (`Ctrl+C`).
7. **Variante para comparar (opcional, discutir en el informe):** repite
   el mismo experimento pero, en vez del paso 4, deja el umbral minimo
   como estaba y cambia el **umbral maximo** a `100`. No hace falta
   capturar de nuevo un pcap completo para esto; basta con observar el
   comportamiento y comparar con el paso 4.

## Preguntas

1. Antes del ataque (lo que anotaste en el paso 2), ¿la valvula de la
   Zona 4 estaba abierta o cerrada? Explica por que, usando la logica de
   histeresis (`si humedad <= umbral_min -> abre`, `si humedad >=
   umbral_max -> cierra`).

2. Ubica en el pcap el paquete `Write Single Register` (FC 06) del paso
   4. ¿Qué direccion y que valor tiene? Verifica con el mapa de registros
   que corresponde al umbral minimo de la Zona 4 (no de otra zona).

3. Con umbral minimo = 0, la condicion `humedad <= umbral_min` deja de
   cumplirse con la valvula cerrada (la humedad tendria que llegar a 0
   exacto). Sabiendo que la humedad simulada esta acotada entre 0 y 100,
   y que baja de a poco cada segundo mientras la valvula este cerrada:
   ¿este ataque es una negacion de riego **permanente**, o solo un
   **retraso**? ¿En que momento, si esperas lo suficiente, se volveria a
   cumplir la condicion y la valvula se abriria sola? ¿Por que, aun
   asi, sigue siendo un ataque efectivo dentro de la ventana de tiempo
   de este laboratorio (15-20 segundos)?

4. Revisa `docker compose logs modbus-master` correspondiente al periodo
   de la captura. ¿Qué humedad y que estado de valvula reporta la Zona 4
   varios ciclos despues del ataque? ¿Coincide con tu prediccion de la
   pregunta 3?

5. En el pcap, cuenta cuantos paquetes de escritura (FC 05 o FC 06) tuvo
   que enviar el atacante para lograr este efecto, y compáralo con cuántos
   habria necesitado si en cambio hubiera optado por forzar la coil de la
   valvula de la Zona 4 directamente a "cerrada" cada vez que el SCADA
   intentara abrirla (como en el Laboratorio 2, pero sosteniendo el
   ataque en el tiempo). ¿Por que la manipulacion de setpoint es una
   tecnica mas "sigilosa" en terminos de trafico de red generado?

6. Redacta, en palabras (no hace falta sintaxis real de Suricata/Zeek),
   una condicion que un IDS podria usar para detectar este tipo de
   ataque basandose solo en lo que se ve en el pcap (function code,
   direccion, valor escrito). Por ejemplo: *"alertar si se observa un
   FC06 escribiendo en alguna de las direcciones de umbral minimo (2, 12,
   22, 32) un valor por debajo de un minimo operativo razonable (ej. 15)"*.
   Ajusta el ejemplo o propon el tuyo propio.

7. (Variante del paso 7) Compara brevemente el efecto de fijar
   `umbral_min = 0` versus `umbral_max = 100`. ¿Ambos logran "negar
   riego" a la zona? ¿Cuál de los dos te parece mas dificil de notar para
   alguien que solo mira el HMI de vez en cuando, y por que?

## Entregable

- `lab3.pcap`
- Informe con las 7 respuestas, incluyendo los valores de humedad/valvula
  anotados antes y despues del ataque (pasos 2 y 4/5), y la evidencia de
  pcap (numero de paquete, direccion, valor) para las preguntas que la
  requieren.
