# Laboratorio 1 - Reconocimiento pasivo del protocolo Modbus TCP

## Objetivos

- Reconocer la estructura de un mensaje Modbus TCP (MBAP Header + PDU)
  directamente sobre una captura real.
- Identificar el patron de *polling* automatico que genera la central
  SCADA (`modbus-master`) sin que nadie toque el HMI.
- Deducir, **solo a partir del trafico capturado** (sin mirar el codigo
  fuente del laboratorio), cuantas zonas de riego existen y que variables
  expone cada una.

## Procedimiento

1. Levanta el laboratorio si no esta corriendo (`docker compose up -d
   --build` dentro de `modbus/`).
2. Entra al contenedor de captura y arranca `tcpdump` guardando a
   `lab1.pcap`:
   ```bash
   docker exec -it modbus-sniffer sh
   tcpdump -i any -n -w /captures/lab1.pcap 'tcp port 502'
   ```
3. **No abras el HMI ni interactues con nada.** Deja correr la captura
   unos 30 segundos, solo con el polling automatico del SCADA.
4. Detén la captura (`Ctrl+C`) y copia `captures/lab1.pcap` a tu maquina.
5. Ábrela con Wireshark, filtro de pantalla `modbus`.

## Preguntas

Responde citando evidencia concreta (numero de paquete, Transaction ID,
valores de los campos) para cada punto.

1. ¿Qué **Unit Identifier** llevan todos los mensajes de la captura?
   ¿Qué representa ese campo dentro del MBAP Header?

2. Lista todos los **Function Codes** distintos que aparecen en la
   captura y explica en una linea que hace cada uno.

3. Busca un paquete `Read Coils` (FC 01). ¿Cuántas coils pide el campo
   *Quantity of Coils*? Sabiendo que cada zona de riego usa exactamente 2
   coils (una para la valvula y otra para el modo manual/automatico),
   ¿a cuantas zonas corresponde ese numero?

4. Elige un paquete `Read Holding Registers` (FC 03) enviado por el
   master. Anota su direccion inicial y la cantidad de registros que
   pide. Sabiendo que cada zona reserva un bloque de 10 holding registers
   consecutivos empezando en `zona_indice * 10`, ¿a que zona (0, 1, 2 o
   3) corresponde ese paquete?

5. Mide el tiempo que pasa entre dos rafagas de polling consecutivas
   (busca el patron que se repite: lecturas de coils + registros +
   discrete inputs, y luego vuelve a empezar). ¿Cuantos segundos son,
   aproximadamente?

6. Segun lo que viste, ¿el dispositivo esclavo (`modbus-slave`) envia
   algun mensaje **por iniciativa propia**, sin que el master se lo pida
   primero? Justifica tu respuesta con lo que dice la seccion 1 de
   `PROTOCOLO-MODBUS.md` sobre el modelo cliente/servidor de Modbus.

7. Fíjate como el master lee los **Discrete Inputs**: a diferencia de las
   coils (que se leen todas juntas en un solo paquete FC 01), ¿pide las
   alarmas de todas las zonas en un unico paquete FC 02, o en varios
   paquetes separados? ¿Cuántos discrete inputs pide cada paquete FC 02
   individual? A partir de eso, y del numero de zonas que dedujiste en la
   pregunta 3, calcula cuantos discrete inputs se leen **en total** por
   cada ronda completa de polling.

## Entregable

- `lab1.pcap`
- Informe con las 7 respuestas, cada una con su evidencia (numero de
  paquete y/o Transaction ID de Wireshark).
