# Pauta de correccion (SOLO DOCENTE)

Respuestas esperadas / rubrica para los tres laboratorios de
`laboratorios/`. No entregar este archivo a los alumnos.

Direcciones de referencia (0-indexado a nivel de protocolo; zona = z+1
en el HMI):

| z | Zona          | HR (humedad, caudal, umin, umax) | Coil valvula | Coil modo | DI (baja, encharc.) |
|---|---------------|-----------------------------------|--------------|-----------|-----------------------|
| 0 | Zona 1 Parronal   | 0, 1, 2, 3     | 0 | 4 | 0, 1 |
| 1 | Zona 2 Hortalizas | 10, 11, 12, 13 | 1 | 5 | 2, 3 |
| 2 | Zona 3 Frutales   | 20, 21, 22, 23 | 2 | 6 | 4, 5 |
| 3 | Zona 4 Vivero     | 30, 31, 32, 33 | 3 | 7 | 6, 7 |

`POLL_SECONDS` por defecto = 2. `UNIT_ID` por defecto = 1.

## Laboratorio 1

1. Unit ID = **1** en todos los mensajes. Es la direccion del dispositivo
   esclavo dentro del bus Modbus (relevante sobre todo en serial
   multi-drop o pasarelas TCP->RTU con varios esclavos detras de una sola
   IP; aqui hay un solo esclavo, por eso siempre es el mismo valor).

2. Deberian aparecer **FC 01, 02, 03 y tambien FC 05**. Punto importante
   a validar en la correccion: aunque la consigna dice "no interactues
   con el HMI", el `modbus-master` reescribe la coil de la valvula de
   **cada** zona en **cada** ciclo de control, incluso si el valor no
   cambia (el codigo llama `write_coil` incondicionalmente dentro de la
   rama "automatico"). Un alumno atento deberia notar y reportar esto: el
   polling "pasivo" del SCADA en realidad ya incluye escrituras.

3. El master lee las coils de todas las zonas en un solo `Read Coils`
   con **Quantity = 8** (direccion inicial 0). 8 coils / 2 coils por zona
   (valvula + modo) = **4 zonas**.

4. Cualquier `Read Holding Registers` con direccion inicial multiplo de
   10 (0, 10, 20 o 30) y `Quantity = 4` es valido; el alumno debe indicar
   a que zona corresponde segun la tabla de arriba.

5. Aproximadamente **2 segundos** entre rondas (coincide con
   `POLL_SECONDS`), con una pequena variacion (unos pocos ms) por el
   tiempo real de red/procesamiento de las 4 zonas dentro de esa ronda.

6. **No.** Modbus es estrictamente cliente-iniciado: el esclavo nunca
   envia nada sin que se lo pidan primero (a diferencia de, por ejemplo,
   DNP3 con "unsolicited responses"). Esto deberia estar respaldado con
   la seccion 1 de `PROTOCOLO-MODBUS.md`.

7. Cada `Read Discrete Inputs` individual pide **Quantity = 2** (los 2
   discrete inputs de una sola zona); hay **4 paquetes FC02 separados**
   por ronda (uno por zona), no uno combinado como en las coils. Total:
   4 x 2 = **8 discrete inputs** leidos por ronda, repartidos en 4
   paquetes.

## Laboratorio 2

1. Dos escrituras FC 05: la primera en direccion **4** (coil de modo de
   la Zona 1, `4 + 0`), la segunda en direccion **0** (coil de la
   valvula de la Zona 1). Son dos escrituras porque el boton "Abrir" del
   HMI (`/api/zonas/<id>/valvula`) siempre fuerza el modo manual **antes**
   de tocar la valvula, para que el cambio no sea sobreescrito por el
   SCADA en su siguiente ciclo.

2. Ambos paquetes llevan valor **`0xFF00`** = **verdadero/ON** (modo
   manual activado, valvula abierta).

3. El paso "Cerrar" (2c) **tambien** escribe ambas coils (modo en
   direccion 4 con `0xFF00`, y valvula en direccion 0 con `0x0000`),
   aunque la zona ya estaba en manual desde el paso 2a. Conclusion
   esperada: el boton **no verifica** el estado actual antes de escribir,
   simplemente fuerza el modo manual en cada click sobre "Abrir"/"Cerrar"
   (implementacion "fire and forget", no idempotente respecto al estado
   previo).

4. El paso "Volver a Automatico" (2e) genera **una sola** escritura FC05,
   en direccion **4** (coil de modo de la Zona 1), con valor **`0x0000`**
   (manual = false). No toca la coil de la valvula: el SCADA la retoma en
   su siguiente ciclo.

5. Durante la ventana en modo manual (entre 2a y 2e), **0 escrituras**
   sobre la coil 0 deberian venir de `modbus-master` (el codigo se salta
   por completo el `write_coil` de esa zona mientras `modo_manual=1`).
   Las unicas escrituras sobre la coil 0 en ese intervalo son las 2 del
   propio alumno (abrir y cerrar). Esto deberia poder confirmarse ademas
   viendo en los logs de `modbus-master` la linea de la Zona 1 con
   `modo=MANUAL (SCADA no interviene)` durante ese periodo.

6. FC06 en direccion **12** (`hr_base(1) + 2` = Zona 2, umbral minimo),
   valor **60** (`0x003C`).

7. **No existe ningun campo de identidad/autenticacion** en el MBAP
   Header (Transaction ID, Protocol ID, Length, Unit ID) ni en la PDU: el
   Unit ID identifica un *dispositivo esclavo*, no un usuario ni un
   cliente autorizado. Implicancia: a nivel de protocolo es imposible
   distinguir una escritura legitima del HMI de una escritura maliciosa
   desde cualquier otro host con acceso de red al puerto 502 -- la unica
   defensa posible tiene que venir de fuera del protocolo (segmentacion
   de red, listas de control de acceso, monitoreo).

## Laboratorio 3

1. Depende del estado real de la Zona 4 al momento de ejecutar (la
   humedad simulada varia). Lo que se evalua es que el alumno **explique
   correctamente la logica de histeresis**: si humedad <= umbral_min
   (30 por defecto) se esperaria abierta; si humedad >= umbral_max (80)
   se esperaria cerrada; si esta entre ambos umbrales, se mantiene el
   ultimo estado (que podria ser cualquiera de los dos segun el
   historial). No hay un valor "correcto" unico aqui, solo el
   razonamiento.

2. FC06 en direccion **32** (`hr_base(3) + 2` = Zona 4, umbral minimo),
   valor **0**.

3. **Es un retraso, no una negacion permanente.** La humedad esta acotada
   entre 0 y 100 (clamp en `slave.py`); con la valvula cerrada, baja
   ~1%/segundo por evapotranspiracion. Con `umbral_min = 0`, la condicion
   `humedad <= 0` recien se cumple cuando la humedad llega **exactamente
   a 0** y queda pegada ahi (el clamp no la deja bajar mas) -- en ese
   momento el SCADA volveria a abrir la valvula. Dependiendo de la
   humedad inicial, esto puede tardar bastante mas que los 15-20 segundos
   de la ventana del laboratorio (por ejemplo, partiendo de 45-50%, unos
   45-50 segundos). Sigue siendo un ataque efectivo dentro de la ventana
   de observacion del laboratorio porque logra su objetivo (impedir el
   riego) durante un tiempo significativo con una unica escritura, aunque
   el sistema termine "autocorrigiendose" en el limite extremo (suelo
   completamente seco).

4. Se espera ver, en los logs de ese periodo, la Zona 4 con `modo=
   AUTOMATICO`, `valvula=CERRADA` y una humedad que sigue bajando ciclo a
   ciclo (ej. 45%, 44%, 43%...), consistente con la explicacion de la
   pregunta 3.

5. El ataque de setpoint necesito **un solo paquete FC06**. Sostener el
   mismo efecto forzando la coil directamente (como en el Laboratorio 2)
   requeriria que el atacante reescribiera la coil **cada vez** que el
   SCADA la reabre (potencialmente cada ciclo de `POLL_SECONDS`,
   indefinidamente) generando muchisimos mas paquetes FC05 a lo largo del
   tiempo. Menos trafico generado = menos oportunidades de que un
   analista o un IDS lo note; ademas, una sola escritura de registro se
   confunde mas facilmente entre el trafico normal de configuracion que
   una guerra de escrituras repetidas sobre la misma coil.

6. Ejemplo de respuesta valida: *"alertar si se observa un FC06 (Write
   Single Register) escribiendo en alguna de las direcciones de umbral
   minimo (2, 12, 22, 32) un valor por debajo de un piso operativo
   razonable (ej. menor a 15)"*. Tambien es valida una regla equivalente
   sobre las direcciones de umbral maximo (3, 13, 23, 33) con un valor
   por encima de un techo razonable (ej. mayor a 90). Se evalua que la
   condicion sea especifica (direccion + function code + rango de valor),
   no una regla generica tipo "alertar ante cualquier escritura".

7. Ambas variantes ("umbral_min=0" y "umbral_max=100") logran negar riego
   por un tiempo, pero por mecanismos opuestos: la primera evita que la
   valvula se **abra**; la segunda evita que se **cierre** una vez
   abierta (de hecho, si la valvula ya estaba abierta, `umbral_max=100`
   la deja regando sin parar, lo que en este proceso simulado termina en
   **encharcamiento**, no en sequia -- un efecto visible y hasta
   ruidoso). Se espera que el alumno note esta asimetria: `umbral_min=0`
   es el mas "sigiloso" de los dos porque su efecto (sequia lenta) es mas
   dificil de notar a simple vista que un encharcamiento con la alarma de
   exceso de riego activada.

## Rubrica sugerida (por laboratorio)

- 40%: correccion tecnica de las respuestas (direcciones, valores,
  function codes correctos).
- 30%: evidencia citada del pcap (numero de paquete / Transaction ID,
  no solo "lo vi en Wireshark").
- 20%: calidad del razonamiento en las preguntas de analisis/impacto
  (no solo describir el paquete, sino explicar el por que).
- 10%: entrega del `.pcap` correspondiente, capturado siguiendo la
  secuencia pedida (permite verificar lo demas).
