# Laboratorio 2 - Control de actuadores con DIRECT_OPERATE

## Objetivos

- Identificar mensajes de control DNP3 (`DIRECT_OPERATE`, function code
  5) y decodificar el objeto CROB (Control Relay Output Block).
- Comprobar experimentalmente que DNP3, igual que Modbus, no autentica ni
  autoriza quien manda un comando.
- Entender y evidenciar en el pcap el mecanismo de modo manual/automatico
  (identico en espiritu al del laboratorio Modbus, aqui implementado con
  una coil DNP3 -- Binary Output/CROB -- en vez de una coil Modbus).

## Procedimiento

Sigue esta secuencia **exacta**. Antes de empezar, asegurate de que todas
las zonas esten en modo Automatico.

1. Arranca la captura:
   ```bash
   docker exec -it dnp3-sniffer sh
   tcpdump -i any -n -w /captures/lab2.pcap 'tcp port 20000'
   ```
2. Abre `http://localhost:9090/dnp3/`. En la tarjeta de la **Zona 1 - Parronal**:
   - a) Click en **"Abrir"**.
   - b) Espera 5 segundos.
   - c) Click en **"Cerrar"**.
   - d) Espera 5 segundos.
   - e) Click en **"Volver a Automatico"**.
3. En la tarjeta de la **Zona 2 - Hortalizas**, cambia el **umbral
   minimo** a `60` y presiona "Aplicar".
4. Espera 5 segundos mas y detén la captura (`Ctrl+C`).

## Preguntas

1. Ubica los paquetes generados por el paso 2a ("Abrir" en Zona 1).
   Deberias encontrar **dos** `DIRECT_OPERATE` (func=5) seguidos, cada
   uno con su `RESPONSE` (func=129). ¿Sobre que grupo/variacion de objeto
   son ambos? ¿Que indice tiene cada uno, y que representa segun el mapa
   de objetos (pista: un indice es para el modo, otro para la valvula)?

2. Abre el detalle de uno de esos objetos CROB en Wireshark. Identifica
   el campo `Control Code` / `Op Type`. ¿Que valor tiene para "abrir" la
   valvula? Revisa `PROTOCOLO-DNP3.md` (o `dnp3lib.py`) y confirma que
   corresponde a `LATCH_ON`.

3. Compara la `RESPONSE` a un `DIRECT_OPERATE` con la `RESPONSE` a un
   `READ` (del Laboratorio 1). Ambas usan function code 129, pero,
   ¿tienen la misma cantidad de objetos? ¿Que campo del CROB cambia entre
   el `DIRECT_OPERATE` (pedido) y su `RESPONSE` (eco), y que significa
   ese cambio?

4. Ahora ubica los paquetes del paso 2c ("Cerrar"). La zona ya estaba en
   modo manual desde el paso 2a. ¿El paso 2c vuelve a escribir el objeto
   de modo de todas formas, o solo el de la valvula? ¿Que te dice esto
   sobre como esta implementado el boton (verifica el estado actual antes
   de mandar el comando, o simplemente lo fuerza cada vez)?

5. Ubica el paquete del paso 2e ("Volver a Automatico"). ¿Cuántos
   `DIRECT_OPERATE` genera, sobre que objeto, y con que Op Type?

6. Filtra los `DIRECT_OPERATE` sobre la coil de la valvula de la Zona 1
   durante el intervalo en que estuvo en modo manual (entre 2a y 2e).
   ¿Cuántos fueron generados por tus clics? Revisa
   `docker compose logs dnp3-master` del mismo periodo y confirma que el
   SCADA no mando ninguno mientras esa zona estuvo en modo manual.

7. Ubica el `DIRECT_OPERATE` del paso 3 (cambio de umbral). ¿Sobre que
   grupo/variacion es? ¿Que indice y que valor trae? Verifica con el mapa
   de objetos que corresponde al umbral minimo de la Zona 2.

8. Revisa el contenido completo (las 3 capas) de cualquiera de estos
   `DIRECT_OPERATE`. ¿Existe algun campo -- en la capa de enlace, de
   transporte, o de aplicacion -- que identifique que el comando vino del
   HMI web "autorizado" y no de cualquier otro cliente conectado al mismo
   puerto 20000? Relaciona tu respuesta con la seccion 5 de
   `PROTOCOLO-DNP3.md` sobre por que este outstation acepta varias
   conexiones a la vez.

## Entregable

- `lab2.pcap`
- Informe con las 8 respuestas, cada una con su evidencia (numero de
  paquete, function code, grupo/variacion/indice, valor).
