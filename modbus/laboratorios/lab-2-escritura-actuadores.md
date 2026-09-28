# Laboratorio 2 - Escritura de actuadores sin autenticacion

## Objetivos

- Identificar mensajes de escritura Modbus (`Write Single Coil` / `Write
  Single Register`) y decodificar sus valores.
- Comprobar experimentalmente que Modbus no autentica ni autoriza quien
  escribe: cualquier cliente en la red puede forzar un actuador.
- Entender y evidenciar en el pcap el mecanismo de **modo manual vs.
  automatico** de este laboratorio.

## Procedimiento

Sigue esta secuencia **exacta** (para que tu pcap sea comparable con el
de tus companeros). Antes de empezar, asegurate de que todas las zonas
esten en modo **Automatico** (si alguna quedo en Manual de una prueba
anterior, usa el boton "Volver a Automatico" antes de capturar).

1. Entra al sniffer y arranca la captura a `lab2.pcap`:
   ```bash
   docker exec -it modbus-sniffer sh
   tcpdump -i any -n -w /captures/lab2.pcap 'tcp port 502'
   ```
2. Abre `http://localhost:9090/modbus/`. En la tarjeta de la **Zona 1 - Parronal**:
   - a) Click en **"Abrir"**.
   - b) Espera 5 segundos (sin hacer nada mas).
   - c) Click en **"Cerrar"**.
   - d) Espera 5 segundos.
   - e) Click en **"Volver a Automatico"**.
3. En la tarjeta de la **Zona 2 - Hortalizas**, cambia el **umbral
   minimo** a `60` y presiona "Aplicar".
4. Espera 5 segundos mas y detén la captura (`Ctrl+C`).

## Preguntas

1. Ubica en el pcap los paquetes generados por el paso 2a ("Abrir" en
   Zona 1). Deberias encontrar **dos** escrituras `Write Single Coil`
   (FC 05) seguidas. ¿En que direccion escribe cada una? Segun el mapa de
   registros de `PROTOCOLO-MODBUS.md`, ¿que representa cada direccion?
   ¿Por que son dos escrituras y no una sola?

2. ¿Que valor (en hexadecimal) llevan esos dos paquetes? Traduce ese
   valor a verdadero/falso.

3. Ahora ubica los paquetes del paso 2c ("Cerrar"). Compáralos con los
   del paso 2a: la zona ya estaba en modo manual desde el paso anterior,
   asi que en teoria no haria falta volver a tocar esa coil. ¿El paso 2c
   escribe la coil de modo de todas formas, o solo escribe la coil de la
   valvula? Con esa evidencia (sin mirar el codigo), ¿que te dice esto
   sobre como esta implementado el boton -- verifica el estado actual
   antes de escribir, o simplemente fuerza el modo manual cada vez que se
   presiona?

4. Ubica el/los paquete(s) del paso 2e ("Volver a Automatico"). ¿Cuántas
   escrituras genera, sobre que direccion, y con que valor?

5. Filtra en Wireshark solo los paquetes `Write Single Coil` dirigidos a
   la **coil de la valvula de la Zona 1** (no a la de modo) durante todo
   el intervalo entre el paso 2a y el paso 2e (mientras esa zona estuvo
   en modo manual). ¿Cuántos de esos paquetes fueron generados por tus
   clics, y cuantos (si hay alguno) por `modbus-master`? Contrasta tu
   respuesta con `docker compose logs modbus-master` del mismo periodo de
   tiempo.

6. Ubica el paquete `Write Single Register` (FC 06) del paso 3. ¿Que
   direccion y que valor tiene? Verifica, usando el mapa de registros,
   que corresponde al umbral minimo de la Zona 2 y no a otra zona u otra
   variable.

7. Sin mirar el codigo fuente: revisa el contenido completo de cualquiera
   de estos paquetes de escritura (MBAP Header + PDU). ¿Existe algun
   campo que identifique que la escritura vino de un usuario "autorizado"
   del HMI web, y no de cualquier otro cliente Modbus en la misma red?
   Justifica tu respuesta y explica en 2-3 lineas la implicancia de
   seguridad de que la respuesta sea "no".

## Entregable

- `lab2.pcap`
- Informe con las 7 respuestas, cada una con su evidencia (numero de
  paquete, Transaction ID, direccion decimal, valor hexadecimal).
