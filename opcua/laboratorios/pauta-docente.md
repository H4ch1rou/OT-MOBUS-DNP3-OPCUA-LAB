# Pauta de correccion (SOLO DOCENTE) - Laboratorios OPC UA

No entregar este archivo a los alumnos.

Arbol de nodos de referencia (namespace propio, tipicamente indice 2):
`Objects/Zonas/Zona{1..4}/{Humedad, Caudal, UmbralMinimo, UmbralMaximo,
Valvula, ModoManual, AlarmaBaja, AlarmaEncharcamiento}`. `POLL_SECONDS`
por defecto = 2. Intervalo de Subscription = 500 ms (hardcodeado en
`opcua/master/master.py`).

## Laboratorio 1

1. `SecurityPolicy = None` (sin firma ni cifrado) y `Anonymous` como tipo
   de identificacion de usuario -- sin credenciales de ningun tipo.

2. Deberian verse varios `Browse`/`TranslateBrowsePathsToNodeIds`
   consecutivos al inicio de la conexion -- uno por cada nivel de la
   ruta (`Zonas`, luego cada `ZonaN`, luego cada una de sus 8 variables).
   Con 4 zonas x 8 variables + los objetos intermedios, se esperan del
   orden de 30-40 resoluciones de nodo en total.

3. El `CreateSubscription` pide un *Requested Publishing Interval* de
   **500 ms**. Es un numero **distinto** de `POLL_SECONDS` (2000 ms): el
   intervalo de Subscription controla que tan seguido el servidor puede
   *avisar* cambios; `POLL_SECONDS` controla el lazo de control manual
   (histeresis) del master, que es un mecanismo aparte.

4. El `CreateMonitoredItems` deberia cubrir **8 variables** (2 alarmas x
   4 zonas): `AlarmaBaja` y `AlarmaEncharcamiento` de cada zona.

5. Un `Read` normal del polling deberia pedir varias variables a la vez
   (tipicamente las 8 variables de una zona, o mas si el alumno mira un
   Read que agrupe varias zonas -- depende de como Wireshark presente el
   ReadRequest, pero el patron esperado es "un Read = varias variables").

6. Deberia notarse que el `Publish` no viene inmediatamente despues de un
   `Read`/`Write` propio del cliente. Buscando hacia atras, debería
   encontrarse un `PublishRequest` anterior (el cliente mantiene
   `PublishRequest` pendientes constantemente, es parte del protocolo de
   Subscriptions: siempre hay al menos uno "en cola" esperando que el
   servidor tenga algo que avisar).

7. La `MonitoredItemNotification` trae el nuevo valor (`true` para
   `AlarmaBaja`). El alumno deberia poder relacionar el orden de creacion
   del `MonitoredItem` correspondiente (posicion en la lista del paso 4)
   con la variable `AlarmaBaja` de la Zona 2.

8. Ambos son mecanismos de "aviso push" iniciados por el servidor. La
   `UNSOLICITED_RESPONSE` de DNP3 es un mensaje verdaderamente espontaneo
   (function code aparte, sin relacion con ningun pedido pendiente); el
   `Publish` de OPC UA responde formalmente a un `PublishRequest` que el
   cliente ya habia dejado pendiente (long-polling). En terminos de
   "facil de configurar mal": OPC UA depende de que el cliente cree
   correctamente la Subscription y el `MonitoredItem` sobre CADA variable
   relevante -- si se olvida una, esa variable nunca avisa nada (mientras
   que en DNP3 el mecanismo de eventos suele ser mas automatico del lado
   del outstation, aunque tambien configurable).

## Laboratorio 2

1. Dos `Write`: uno sobre `Zona1/ModoManual` (valor `true`), otro sobre
   `Zona1/Valvula` (valor `true`). Son dos porque el HMI
   (`/api/zonas/<id>/valvula` en `webhmi/app.py`) siempre fuerza el modo
   manual antes de tocar la valvula, igual que en los otros dos
   laboratorios.

2. `VariantType = Boolean` para ambos -- coincide con el tipo declarado
   de esas variables en el servidor.

3. El valor escrito en OPC UA es minimo (un solo booleano, sin campos
   adicionales), muy distinto a los 11 bytes estructurados del CROB de
   DNP3 (que incluye tipo de operacion, contador de repeticiones, tiempos
   de encendido/apagado, y un campo de status en la respuesta). Lo que se
   "pierde" es la semantica rica de control (pulsos, temporizacion,
   confirmacion de resultado detallada) -- en OPC UA esa logica quedaria
   del lado de la aplicacion, no del protocolo.

4. Si, el paso 2c **tambien** escribe `ModoManual` (aunque ya estaba en
   `true`), ademas de `Valvula`. Conclusion esperada: el boton no
   verifica el estado actual antes de escribir, simplemente fuerza el
   modo manual en cada click sobre "Abrir"/"Cerrar" (mismo patron que
   Modbus y DNP3).

5. Un solo `Write`, sobre `Zona1/ModoManual`, con valor `false`.

6. Durante la ventana en modo manual, **0 escrituras** sobre
   `Zona1/Valvula` deberian venir de `opcua-master` (su codigo se salta
   por completo el `write_value` de esa zona mientras `ModoManual=true`).
   Los logs de `opcua-master` deberian mostrar
   `modo=MANUAL (SCADA no interviene)` para la Zona 1 durante ese
   periodo.

7. `Write` sobre `Zona2/UmbralMinimo`, valor `60.0` (Double).

8. **No.** Ni la sesion (`ActivateSession` anonima) ni la capa de mensaje
   `Write` llevan ninguna identidad de "aplicacion cliente" verificable --
   cualquier cliente OPC UA que abra una sesion anonima contra este
   servidor puede escribir exactamente lo mismo que el HMI web, incluido
   `opcua-operador`. Esto es coherente con la seccion 4 de
   `PROTOCOLO-OPCUA.md`: OPC UA SI define mecanismos de seguridad
   (certificados, autenticacion), pero este laboratorio los deja
   desactivados a proposito.

## Laboratorio 3

1. Depende del estado real al momento de ejecutar. Se evalua que el
   alumno explique correctamente la logica de histeresis (mismo criterio
   que en las pautas de Modbus/DNP3).

2. `Write` sobre `Zona4/UmbralMinimo`, valor `0.0`.

3. **Es un retraso, no una negacion permanente**: la humedad esta acotada
   entre 0 y 100; con `UmbralMinimo=0` la condicion `humedad <= 0` recien
   se cumple cuando la humedad llega exactamente a 0 y queda pegada ahi,
   momento en el que el SCADA reabriria la valvula. Sigue siendo efectivo
   durante la ventana del laboratorio porque logra su objetivo (negar
   riego) por un tiempo significativo con un solo mensaje.

4. Deberia aparecer un `Publish` con una `MonitoredItemNotification`
   sobre `Zona4/AlarmaBaja` con valor `true`.

5. El master deberia registrar la alarma **casi de inmediato** (apenas le
   llega el `Publish`, procesado por su handler de Subscription en
   paralelo al lazo de control) -- no tiene que esperar a su siguiente
   `Read` programado. Verificar comparando el timestamp del log
   `SUBSCRIPTION: ... cambio a True` contra el del siguiente `Read`
   programado.

6. Ambos avisan casi de inmediato, pero por mecanismos distintos: DNP3 lo
   hace con un function code dedicado y espontaneo
   (`UNSOLICITED_RESPONSE`); OPC UA lo hace respondiendo a un
   `PublishRequest` que el cliente ya tenia pendiente (long-polling,
   parte formal del protocolo de Subscriptions). En la practica, ambos
   son mucho mas rapidos que el polling puro de Modbus.

7. El atacante mando **1** `Write`. El propio sistema genero como minimo
   1 mensaje adicional (el `Publish` con la notificacion; a diferencia de
   DNP3, aqui no hay un `CONFIRM` explicito por cada notificacion
   individual -- el `PublishResponse` en si cumple ese rol dentro del
   protocolo). El punto sigue siendo el mismo: el ataque en si es
   sigiloso (1 mensaje), pero su efecto se anuncia solo.

8. Respuestas validas: (a) sobre el `Write` original -- *"alertar si se
   escribe una variable `UmbralMinimo` con un valor por debajo de un piso
   razonable (ej. menor a 15)"*; o (b) una regla de correlacion -- *"alertar
   si aparece una notificacion `Publish` sobre una variable de alarma
   dentro de los N segundos siguientes a un `Write` sobre una variable de
   umbral de la misma zona"*.

## Rubrica sugerida (por laboratorio)

- 40%: correccion tecnica (Services, variables/NodeIds, valores
  correctos).
- 30%: evidencia citada del pcap (numero de paquete, campos exactos de
  Wireshark, no solo "lo vi").
- 20%: calidad del razonamiento en las preguntas de analisis/impacto y de
  comparacion entre protocolos.
- 10%: entrega del `.pcap` correspondiente, capturado siguiendo la
  secuencia pedida (incluyendo el reinicio de `opcua-master` en el
  Laboratorio 1).
