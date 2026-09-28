# Pauta de correccion (SOLO DOCENTE) - Laboratorios DNP3

No entregar este archivo a los alumnos.

Indices de referencia (0-indexado a nivel de protocolo; zona = z+1 en el
HMI). Cada grupo de objetos tiene su PROPIO espacio de indices:

| z | Zona          | Analog Input (hum,caudal) | Analog Output (umin,umax) | Binary Input (baja,ench) | Binary Output/CROB (valvula,modo) |
|---|---------------|-----------------------------|------------------------------|-----------------------------|---------------------------------------|
| 0 | Zona 1 Parronal   | 0, 1 | 0, 1 | 0, 1 | 0, 1 |
| 1 | Zona 2 Hortalizas | 2, 3 | 2, 3 | 2, 3 | 2, 3 |
| 2 | Zona 3 Frutales   | 4, 5 | 4, 5 | 4, 5 | 4, 5 |
| 3 | Zona 4 Vivero     | 6, 7 | 6, 7 | 6, 7 | 6, 7 |

`POLL_SECONDS` por defecto = 2. Direcciones DNP3 de estacion: master = 1,
outstation = 10. Function codes: CONFIRM=0, READ=1, DIRECT_OPERATE=5,
RESPONSE=129 (0x81), UNSOLICITED_RESPONSE=130 (0x82).

## Laboratorio 1

1. En un mensaje del master, `Source=1` (direccion del master),
   `Destination=10` (outstation). En uno del outstation, al reves:
   `Source=10`, `Destination=1`. El control byte de enlace tambien
   difiere: `0xC4` (master) vs `0x44` (outstation).

2. Objeto `Group 60, Variation 1` (Class 0 Data), calificador "sin rango
   / todos los objetos" (0x06). Es el pedido estandar de "integrity
   poll": dame todos los datos estaticos actuales, de todos los grupos.

3. La RESPONSE trae 4 Object Headers: `Group 1 Var 2` (Binary Input,
   8 puntos), `Group 10 Var 2` (Binary Output Status, 8 puntos),
   `Group 30 Var 5` (Analog Input, 8 puntos), `Group 40 Var 2` (Analog
   Output Status, 8 puntos). 8 puntos / 2 por zona = **4 zonas**.

4. Aproximadamente **2 segundos** (coincide con `POLL_SECONDS`).

5. La UNSOLICITED_RESPONSE generada por el ataque a la Zona 2 (indice 2
   en Binary Input) tiene su **propio numero de secuencia**, independiente
   del contador de secuencias que usa el master para sus READ. Al
   comparar con los READ cercanos en tiempo (que siguen su propia
   numeracion incremental 0,1,2,3...), el alumno deberia notar que el
   numero de la UNSOLICITED_RESPONSE no continua esa serie -- tiene su
   propia numeracion, empezando en 0 la primera vez que el outstation
   manda una. El bit adicional activado es **UNS** (Unsolicited, bit 4
   del Application Control), que no aparece en una RESPONSE solicitada
   normal.

6. El CONFIRM lleva el **mismo numero de secuencia** que la
   UNSOLICITED_RESPONSE que confirma, con el bit UNS tambien activado --
   asi el outstation sabe cual evento especifico fue confirmado (util si
   hubiera varias unsolicited pendientes, aunque en este laboratorio solo
   hay una a la vez).

7. `Group 1 Var 2` (Binary Input). El indice reportado debe ser 2 o 3
   (o ambos): indice 2 = alarma de humedad baja de la Zona 2 (`z=1`,
   `z*2+0=2`); indice 3 = alarma de encharcamiento de la misma zona
   (`z*2+1=3`). Formula: `zona = indice // 2`, `cual = indice % 2`
   (0=baja, 1=encharcamiento).

8. Porque Modbus es estrictamente cliente-iniciado: el esclavo Modbus NO
   tiene ningun mecanismo para enviar un mensaje sin que el master lo
   pida primero (no existe un equivalente a UNSOLICITED_RESPONSE en el
   protocolo). El unico modo de que el master Modbus se entere de un
   cambio es preguntando (polling), nunca al reves.

## Laboratorio 2

1. Ambos DIRECT_OPERATE son sobre `Group 12 Var 1` (CROB). El primero en
   indice **1** (`zona*2+1` con `zona=0` -> modo manual de la Zona 1); el
   segundo en indice **0** (`zona*2` -> valvula de la Zona 1). Son dos
   comandos porque el HMI (`/api/zonas/<id>/valvula` en `app.py`) siempre
   fuerza el modo manual **antes** de tocar la valvula, para que el
   SCADA no la sobreescriba en su siguiente ciclo.

2. El campo es `Control Code` (que empaqueta el Op Type en los bits
   bajos). Para abrir la valvula se usa **Op Type = 3 (LATCH_ON)**;
   para cerrarla, **Op Type = 4 (LATCH_OFF)**.

3. Si, misma cantidad de objetos (un CROB por comando). Lo que cambia es
   el campo **Status** dentro del CROB: en el pedido (`DIRECT_OPERATE`)
   va en 0 (sin usar); en la RESPONSE, el outstation lo llena con el
   resultado de la operacion -- **0 = SUCCESS** en este laboratorio,
   ya que no simulamos fallas de actuador.

4. Si, el paso 2c **tambien** escribe el objeto de modo (indice 1) ademas
   del de la valvula (indice 0), aunque la zona ya estaba en manual.
   Conclusion esperada: el boton **no verifica** el estado actual antes
   de mandar el comando, simplemente fuerza el modo manual en cada click
   sobre "Abrir"/"Cerrar" (igual que en el laboratorio Modbus).

5. Un solo `DIRECT_OPERATE`, sobre `Group 12 Var 1`, indice **1** (modo
   de la Zona 1), con **Op Type = 4 (LATCH_OFF)** -- vuelve el punto de
   modo a "automatico" sin tocar la valvula.

6. Durante la ventana en modo manual, **0 DIRECT_OPERATE** sobre el
   indice 0 (valvula) deberian venir de `dnp3-master` -- su codigo se
   salta por completo el `operar_valvula` de esa zona mientras
   `modo_manual=True`. Los logs de `dnp3-master` deberian mostrar
   `modo=MANUAL (SCADA no interviene)` para la Zona 1 durante ese
   periodo.

7. `Group 41 Var 2` (Analog Output command, 16-bit), indice **2**
   (`hr equivalente`: `zona*2` con `zona=1` -> umbral minimo de la
   Zona 2), valor **60**.

8. **No.** Ni el direccionamiento de estacion (Source/Destination, que
   identifican dispositivos, no usuarios), ni la capa de aplicacion,
   traen ningun campo de identidad o autenticacion. Cualquier cliente que
   logre conectarse al puerto 20000 puede mandar exactamente los mismos
   bytes que mandaria el HMI legitimo -- de ahi que este laboratorio
   acepte varias conexiones simultaneas a proposito (ver seccion 5 de
   `PROTOCOLO-DNP3.md`): refleja que un outstation real mal configurado
   tiene el mismo problema.

## Laboratorio 3

1. Depende del estado real al momento de ejecutar. Se evalua que el
   alumno explique la logica de histeresis correctamente (igual criterio
   que en la pauta de Modbus).

2. `Group 41 Var 2` (Analog Output command), indice **6**
   (`zona*2` con `zona=3` -> umbral minimo de la Zona 4), valor **0**.

3. **Es un retraso, no una negacion permanente** (mismo razonamiento que
   en Modbus): la humedad esta acotada 0-100; con `umbral_min=0` la
   condicion `humedad <= 0` recien se cumple cuando la humedad llega
   exactamente a 0 y queda pegada ahi por el clamp, momento en el que el
   SCADA reabriria la valvula. Sigue siendo efectivo durante la ventana
   del laboratorio porque logra su objetivo (negar riego) por un tiempo
   significativo con un solo mensaje.

4. Debe aparecer una `UNSOLICITED_RESPONSE` con objeto `Group 1 Var 2`,
   indice **6** (alarma de humedad baja de la Zona 4, `zona*2` con
   `zona=3`).

5. El master deberia registrar la alarma **de inmediato**, en el momento
   en que procesa la UNSOLICITED_RESPONSE (su `receptor()` la atiende tan
   pronto llega, en paralelo al bucle de polling) -- no tiene que esperar
   a su siguiente integrity poll. Verificar comparando el timestamp del
   log `<- UNSOLICITED_RESPONSE ... SIN HABER SIDO PEDIDA` contra el
   timestamp del siguiente `READ` programado.

6. **Mas dificil de pasar desapercibido en DNP3.** A diferencia de
   Modbus, donde el master solo se entera del cambio en su proximo poll
   (hasta `POLL_SECONDS` de demora), en DNP3 el outstation avisa la
   alarma de inmediato por su cuenta. La respuesta esperada debe notar
   que esto es, en cierto sentido, una ventaja defensiva "gratis" del
   protocolo DNP3 frente a Modbus para este tipo de escenario -- aunque
   el ataque en si (la escritura del umbral) sigue siendo igual de facil
   en ambos protocolos.

7. El atacante mando **1** `DIRECT_OPERATE`. El propio sistema, como
   consecuencia, genero al menos 2 mensajes adicionales (la
   `UNSOLICITED_RESPONSE` y su `CONFIRM`). Es decir, el proceso fisico
   reaccionando genero MAS trafico "delator" que el ataque original --
   un punto interesante: el ataque en si es sigiloso (1 paquete), pero su
   *efecto* no lo es, porque el protocolo reporta el sintoma solo.

8. Respuestas validas: (a) sobre el `DIRECT_OPERATE` original, similar a
   la regla de Modbus -- *"alertar si se ve un DIRECT_OPERATE (func=5)
   sobre Group 41 indices pares [0,2,4,6] (umbrales minimos) con un valor
   por debajo de un piso razonable"*; o (b) una regla de correlacion mas
   especifica -- *"alertar si aparece una UNSOLICITED_RESPONSE de Binary
   Input (alarma) dentro de los N segundos siguientes a un DIRECT_OPERATE
   sobre un Analog Output de la misma zona"*, que tiene menos falsos
   positivos porque exige ver el sintoma Y la causa probable juntos.

## Rubrica sugerida (por laboratorio)

- 40%: correccion tecnica (function codes, grupos/variaciones,
  indices/valores correctos).
- 30%: evidencia citada del pcap (numero de paquete, campos exactos de
  Wireshark, no solo "lo vi").
- 20%: calidad del razonamiento en las preguntas de analisis/impacto.
- 10%: entrega del `.pcap` correspondiente, capturado siguiendo la
  secuencia pedida.
