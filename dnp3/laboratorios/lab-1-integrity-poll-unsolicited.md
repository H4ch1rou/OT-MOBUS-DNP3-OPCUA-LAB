# Laboratorio 1 - Integrity poll y respuestas no solicitadas

## Objetivos

- Reconocer las 3 capas de un mensaje DNP3 (enlace, transporte,
  aplicacion) directamente sobre una captura real.
- Entender la estructura de un *integrity poll* (READ sobre Class 0) y
  de su RESPONSE con varios grupos de objetos.
- Observar, con evidencia de pcap, la diferencia central frente a Modbus:
  el outstation puede **iniciar** la comunicacion por su cuenta con una
  `UNSOLICITED_RESPONSE`.

## Procedimiento

1. Levanta el laboratorio si no esta corriendo (`docker compose up -d
   --build` dentro de `dnp3/`). Verifica que todas las zonas esten en
   modo Automatico (si alguna quedo en Manual de una prueba anterior,
   devuelvela con `operador`, opcion 6).

2. Activa la captura:
   ```bash
   docker exec -it dnp3-sniffer sh
   tcpdump -i any -n -w /captures/lab1.pcap 'tcp port 20000'
   ```

3. Deja correr unos 10 segundos **sin tocar nada**, solo observando el
   polling automatico del SCADA.

4. En otra terminal, conecta la consola de operador y fuerza la
   **Zona 2 - Hortalizas** a modo manual con la valvula cerrada:
   ```bash
   docker compose run --rm operador
   ```
   Elige la opcion **5** (forzar cierre manual) sobre la Zona 2, y luego
   la opcion **0** para salir.

5. Vuelve a la terminal del sniffer y espera (sin hacer nada mas) hasta
   ver aparecer un paquete con function code 130 (`UNSOLICITED_RESPONSE`)
   -- deberia tardar bajo un minuto, ya que la humedad de esa zona baja
   ~1%/segundo con la valvula cerrada.

6. Detén la captura (`Ctrl+C`) y copia `captures/lab1.pcap` a tu maquina.
   Ábrela con Wireshark, filtro de pantalla `dnp3`.

## Preguntas

1. Elige cualquier paquete DNP3 y, en el panel de detalle de Wireshark,
   identifica los 3 bloques: "Data Link Layer", "Transport Control" y
   "Application Layer". ¿Qué direccion (`Source`/`Destination`) tiene la
   capa de enlace en un mensaje del master? ¿Y en uno del outstation?

2. Busca un paquete `READ` (`dnp3.al.func == 1`). ¿Qué grupo y variacion
   de objeto pide, y con que calificador? Explica en tus palabras que
   significa ese objeto especifico (pista: es el mismo en todos los READ
   de este laboratorio, es el "pedilo todo").

3. Busca la `RESPONSE` (`dnp3.al.func == 129`) inmediatamente siguiente.
   Lista los distintos "Object Header" que contiene (grupo/variacion de
   cada uno) y cuantos puntos trae cada uno. A partir de eso, y sabiendo
   que cada zona usa 2 indices por grupo, calcula cuantas zonas hay.

4. Mide el tiempo entre dos READ consecutivos del master. ¿Coincide con
   `POLL_SECONDS` en `docker-compose.yml`?

5. Ubica el paquete `UNSOLICITED_RESPONSE` (`dnp3.al.func == 130`) que
   generaste en el paso 5. Sin mirar el codigo fuente:
   - ¿Qué numero de secuencia de aplicacion tiene?
   - ¿Ese numero sigue la secuencia de los READ del master, o parece un
     contador aparte? Justifica con al menos dos numeros de secuencia de
     READ cercanos en tiempo, comparados con el de esta respuesta.
   - ¿Qué bit del Application Control esta activado que NO aparece en
     una RESPONSE normal?

6. Ubica el `CONFIRM` (`dnp3.al.func == 0`) que sigue a la
   UNSOLICITED_RESPONSE. ¿Que numero de secuencia lleva, y por que tiene
   que coincidir con el de la UNSOLICITED_RESPONSE que confirma?

7. En el mismo paquete UNSOLICITED_RESPONSE, revisa el "Object Header"
   que trae. ¿Que grupo/variacion es? Segun el indice que reporta,
   ¿corresponde a la Zona 2 (la que forzaste)? Muestra el calculo
   (indice -> zona) usando la formula de `PROTOCOLO-DNP3.md`.

8. En una o dos frases: ¿por que este mismo experimento (forzar una zona
   a modo manual y esperar a que baje su humedad) **nunca** generaria en
   el laboratorio Modbus un paquete iniciado por el esclavo? Relacionalo
   con la seccion 1 de `PROTOCOLO-DNP3.md`.

## Entregable

- `lab1.pcap`
- Informe con las 8 respuestas, cada una con su evidencia (numero de
  paquete y/o campos exactos de Wireshark).
