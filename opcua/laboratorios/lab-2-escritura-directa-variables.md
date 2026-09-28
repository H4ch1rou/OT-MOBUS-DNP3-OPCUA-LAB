# Laboratorio 2 - Escritura directa de variables

## Objetivos

- Identificar mensajes `Write` de OPC UA y relacionarlos con la variable
  exacta que modifican.
- Comprobar que, a diferencia de Modbus (coils) y DNP3 (CROB), OPC UA no
  usa un objeto de comando especial para controlar un actuador: se
  escribe la variable directo.
- Comprobar experimentalmente que OPC UA, en esta configuracion sin
  seguridad, tampoco autentica ni autoriza quien escribe.

## Procedimiento

Sigue esta secuencia **exacta**. Antes de empezar, asegurate de que todas
las zonas esten en modo Automatico.

1. Arranca la captura:
   ```bash
   docker exec -it opcua-sniffer sh
   tcpdump -i any -n -w /captures/lab2.pcap 'tcp port 4840'
   ```
2. Abre `http://localhost:9090/opcua/`. En la tarjeta de la
   **Zona 1 - Parronal**:
   - a) Click en **"Abrir"**.
   - b) Espera 5 segundos.
   - c) Click en **"Cerrar"**.
   - d) Espera 5 segundos.
   - e) Click en **"Volver a Automatico"**.
3. En la tarjeta de la **Zona 2 - Hortalizas**, cambia el **umbral
   minimo** a `60` y presiona "Aplicar".
4. Espera 5 segundos mas y detén la captura (`Ctrl+C`).

## Preguntas

1. Ubica los mensajes generados por el paso 2a ("Abrir" en Zona 1).
   Deberias encontrar **dos** `Write` seguidos (cada uno con su
   respuesta). ¿Sobre que variables son? (pista: una es `ModoManual`,
   otra es `Valvula`, ambas dentro de `Zona1`). ¿Que NodeId o BrowseName
   identifica cada una en el pcap?

2. Abre el detalle de uno de esos `Write` en Wireshark. ¿Que tipo de dato
   (`VariantType`) tiene el valor escrito? ¿Coincide con lo que esperarias
   para una variable `Boolean`?

3. Compara la estructura de este `Write` con un `DIRECT_OPERATE` de CROB
   del laboratorio DNP3 (si ya lo hiciste). En DNP3, el objeto CROB tiene
   11 bytes con varios campos (OpType, count, tiempos, status). Aqui en
   OPC UA, ¿que tan grande y que tan simple es el valor escrito en
   comparacion? ¿Que perdiste (en términos de opciones de control) al no
   tener un objeto de comando dedicado?

4. Ahora ubica los mensajes del paso 2c ("Cerrar"). La zona ya estaba en
   modo manual desde el paso 2a. ¿El paso 2c vuelve a escribir
   `ModoManual` de todas formas, o solo `Valvula`? ¿Que te dice esto
   sobre como esta implementado el boton (verifica el estado actual antes
   de escribir, o simplemente lo fuerza cada vez)?

5. Ubica el mensaje del paso 2e ("Volver a Automatico"). ¿Cuántos `Write`
   genera, sobre que variable, y con que valor?

6. Filtra los `Write` sobre `Zona1/Valvula` durante el intervalo en que
   estuvo en modo manual (entre 2a y 2e). ¿Cuántos fueron generados por
   tus clics? Revisa `docker compose logs opcua-master` del mismo periodo
   y confirma que el SCADA no escribio esa variable mientras estuvo en
   modo manual.

7. Ubica el `Write` del paso 3 (cambio de umbral). ¿Sobre que variable es
   (`Zona2/UmbralMinimo`)? ¿Que valor trae?

8. Revisa el contenido completo de cualquiera de estos `Write` -- incluida
   la capa de sesion (`ActivateSession` al inicio de la conexion). ¿Existe
   algun campo que identifique que la escritura vino del HMI web
   "autorizado" y no de cualquier otro cliente OPC UA conectado (por
   ejemplo, `opcua-operador`, que se conecta exactamente igual, con la
   misma sesion anonima)? Relaciona tu respuesta con la seccion 4 de
   `PROTOCOLO-OPCUA.md` sobre seguridad en OPC UA.

## Entregable

- `lab2.pcap`
- Informe con las 8 respuestas, cada una con su evidencia (numero de
  paquete, Service, variable, valor).
