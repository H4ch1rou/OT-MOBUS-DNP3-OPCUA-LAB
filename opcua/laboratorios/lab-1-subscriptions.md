# Laboratorio 1 - Conexion, Browse y Subscriptions

## Objetivos

- Reconocer la secuencia de conexion de un cliente OPC UA (sesion,
  navegacion del espacio de nodos) directamente sobre una captura real.
- Entender como el master arma una **Subscription** para enterarse de
  cambios sin hacer polling.
- Observar, con evidencia de pcap, el mecanismo de aviso "push" nativo de
  OPC UA (`Publish`), y compararlo con lo visto en Modbus (solo polling)
  y DNP3 (unsolicited hecho a mano).

## Procedimiento

**Importante**: la conexion inicial de `opcua-master` (sesion, Browse,
creacion de la Subscription) sucede **una sola vez**, apenas arranca el
contenedor. Si el laboratorio ya lleva un rato corriendo, esa secuencia
ya paso y no la vas a ver. Por eso, en este laboratorio vamos a
**reiniciar** `opcua-master` mientras capturamos, para verla completa.

1. Levanta el laboratorio si no esta corriendo (`docker compose up -d
   --build` desde la raiz del repositorio).
2. Activa la captura:
   ```bash
   docker exec -it opcua-sniffer sh
   tcpdump -i any -n -w /captures/lab1.pcap 'tcp port 4840'
   ```
3. En otra terminal, reinicia el master para forzar una reconexion
   limpia mientras capturas:
   ```bash
   docker compose restart opcua-master
   ```
4. Espera unos 10 segundos (para que se complete la conexion y al menos
   un par de ciclos de polling).
5. En otra terminal, conecta la consola de operador y fuerza la
   **Zona 2 - Hortalizas** a modo manual con la valvula cerrada:
   ```bash
   docker compose run --rm opcua-operador
   ```
   Elige la opcion **5** (forzar cierre manual) sobre la Zona 2, y luego
   la opcion **0** para salir.
6. Vuelve a la terminal del sniffer y espera (sin hacer nada mas) hasta
   ver aparecer trafico adicional -- la humedad de esa zona baja
   ~1%/segundo con la valvula cerrada, deberia tardar bajo un minuto en
   activar la alarma.
7. Detén la captura (`Ctrl+C`) y copia `captures/lab1.pcap` a tu maquina.
   Ábrela con Wireshark, filtro de pantalla `opcua`.

## Preguntas

1. Ubica los primeros mensajes de la captura (`CreateSession`,
   `ActivateSession`). ¿Que politica de seguridad y que tipo de
   identificacion de usuario usa `opcua-master` para conectarse? (pista:
   revisa los campos dentro de `ActivateSession` -- deberia ser
   anonimo/sin cifrar).

2. Busca los mensajes `Browse` y/o `TranslateBrowsePathsToNodeIds`
   inmediatamente despues. ¿Cuantas veces aparecen, aproximadamente? A
   partir de eso, estima cuantos nodos (zonas x variables) tuvo que
   resolver el master antes de poder leer o escribir nada.

3. Ubica un mensaje `CreateSubscription`. ¿Que intervalo de publicacion
   (*Requested Publishing Interval*) pide el cliente? Compara ese valor
   con `POLL_SECONDS` -- ¿son el mismo numero o son cosas distintas? (
   pista: uno es del lazo de control manual del master, el otro es del
   mecanismo de Subscription).

4. Busca el `CreateMonitoredItems` que sigue. ¿Sobre cuantas variables
   (NodeIds) se crea el monitoreo? Deberia coincidir con las 2 alarmas x
   4 zonas.

5. Despues de la conexion, busca un `Read` normal (del polling
   automatico). ¿Cuantas variables pide leer en un solo mensaje?

6. Ubica el mensaje `Publish` generado por el paso 5-6 (cuando forzaste
   la Zona 2 y su alarma se activo). Sin mirar el codigo fuente:
   - ¿Este `Publish` viene inmediatamente despues de un `Read` o un
     `Write` del cliente, o parece "suelto"?
   - Busca hacia atras en el tiempo: ¿encuentras un `PublishRequest`
     anterior del cliente, posiblemente varios segundos o minutos antes?
     Esa es la particularidad del mecanismo: el cliente deja pedidos
     `Publish` pendientes, y el servidor responde cuando **el** tiene
     algo que avisar, no cuando el cliente pregunta.

7. Dentro de ese `Publish`, identifica la `MonitoredItemNotification`
   correspondiente. ¿Que valor trae? Relaciona el `ClientHandle` (o el
   orden de creacion en el `CreateMonitoredItems` del paso 4) con la
   variable `AlarmaBaja` de la Zona 2.

8. En 2-3 frases: compara este mecanismo con la `UNSOLICITED_RESPONSE` de
   DNP3 (Laboratorio 1 de ese protocolo). ¿En que se parecen
   conceptualmente? ¿Cual te parece mas facil de configurar mal (por
   ejemplo, dejando el intervalo de publicacion demasiado largo, o
   olvidando crear el `MonitoredItem` de una variable importante)?

## Entregable

- `lab1.pcap`
- Informe con las 8 respuestas, cada una con su evidencia (numero de
  paquete y/o Service name de Wireshark).
