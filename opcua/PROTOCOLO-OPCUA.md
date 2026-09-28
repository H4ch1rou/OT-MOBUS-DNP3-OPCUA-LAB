# Protocolo OPC UA - Guia de referencia y analisis de capturas

> Complemento de [`README.md`](README.md) (como levantar el laboratorio) y
> del [indice general](../README.md) de protocolos. Si no has visto los
> laboratorios de [Modbus](../modbus/README.md) y [DNP3](../dnp3/README.md)
> todavia, vale la pena hacerlos primero: este documento asume que conoces
> esos conceptos basicos y se enfoca en lo que es distinto en OPC UA.

## 1. Que es OPC UA

OPC UA (Open Platform Communications Unified Architecture) es un estandar
mas reciente (2006 en adelante, IEC 62541) pensado para reemplazar al OPC
Classic (basado en tecnologias Windows/COM de los 90). A diferencia de
Modbus y DNP3 -- protocolos de campo, pensados para hablar con un RTU o
PLC especifico -- OPC UA se disenio como un protocolo de **integracion**:
modela cualquier sistema (un PLC, una base de datos, un MES) como un
**espacio de nodos** navegable, orientado a objetos, independiente del
fabricante y de la plataforma.

Sigue existiendo un modelo cliente/servidor, pero con un vocabulario
distinto: el que expone los datos se llama **servidor** (aqui,
`opcua-server`, equivalente al esclavo Modbus / outstation DNP3), y el
que consulta se llama **cliente** (aqui, `opcua-master`, nuestra "central
SCADA").

> OPC UA ofrece una tercera forma de enterarse de cambios, distinta a las
> otras dos: ademas de poder hacer *polling* (como Modbus) tiene
> **Subscriptions** nativas y estandarizadas -- el cliente se suscribe a
> una o mas variables y el servidor le empuja una notificacion cada vez
> que cambian, con un intervalo de publicacion negociado. A diferencia de
> la `UNSOLICITED_RESPONSE` de DNP3 (que tuvimos que modelar a mano
> porque no existe una libreria DNP3 completa en Python), esta
> funcionalidad viene **integrada** en la libreria real que usa este
> laboratorio (`asyncua`).

## 2. Modelo de datos: espacio de nodos

En vez de "tablas" (Modbus) o "grupos de objetos por indice" (DNP3), OPC
UA organiza todo como un **arbol de nodos**, cada uno con un `NodeId`
unico (namespace + identificador) y relaciones (`Organizes`,
`HasComponent`, etc.) hacia otros nodos. Los tipos de nodo mas relevantes
aqui:

- **Object**: agrupa otros nodos (como una carpeta). En este laboratorio,
  `Objects/Zonas/Zona1` es un Object.
- **Variable**: contiene un valor tipado (Double, Boolean, etc.), con un
  **AccessLevel** que determina si se puede leer y/o escribir.

### Arbol de nodos de este laboratorio

```
Objects
  Zonas                       (namespace propio: "http://riego.local/")
    Zona1 .. Zona4
      Humedad              (Double, solo lectura)
      Caudal               (Double, solo lectura)
      UmbralMinimo         (Double, escribible)
      UmbralMaximo         (Double, escribible)
      Valvula              (Boolean, escribible)
      ModoManual           (Boolean, escribible)
      AlarmaBaja           (Boolean, solo lectura)
      AlarmaEncharcamiento (Boolean, solo lectura)
```

El **namespace** (`http://riego.local/`) es una URI que identifica nuestro
espacio de nodos propio, separado del namespace estandar de OPC UA
(namespace 0). Al conectarse, un cliente pide el **namespace index**
correspondiente a esa URI (en este laboratorio, tipicamente `2`) y arma
las rutas de navegacion con ese indice, por ejemplo `2:Zonas`, `2:Zona1`,
`2:Humedad`.

### Como se escribe un actuador: SIN objeto de comando

Esta es la diferencia mas notoria frente a Modbus (coils, FC 05) y DNP3
(CROB, DIRECT_OPERATE): en OPC UA, si una variable tiene AccessLevel de
escritura, el cliente simplemente hace un **Write** directo sobre esa
variable -- no existe un objeto de comando separado como el CROB. Este
laboratorio expone `Valvula` y `ModoManual` como variables booleanas
escribibles: abrir la valvula es, literalmente, escribir `true` en
`Zona1/Valvula`. Esto es realista (asi se hace en muchas integraciones
OPC UA reales para salidas simples) y tambien mas permisivo: no hay ni
siquiera la ceremonia de un objeto de control, solo un Write comun.

## 3. Servicios OPC UA usados en este laboratorio

OPC UA no habla de "function codes" como Modbus/DNP3, sino de
**Services** agrupados en conjuntos (Attribute Services, Subscription
Services, etc.). Los que veras en la captura:

| Service                     | Uso en este laboratorio                                      |
|-------------------------------|------------------------------------------------------------------|
| `CreateSession` / `ActivateSession` | Handshake inicial de conexion (sin autenticacion en este lab: sesion anonima) |
| `Browse` / `TranslateBrowsePathsToNodeIds` | El cliente navega el arbol de nodos para encontrar cada variable |
| `Read`                        | Lee el valor actual de una o mas variables                       |
| `Write`                       | Escribe un valor nuevo en una variable (abrir valvula, cambiar umbral) |
| `CreateSubscription`          | El master crea una suscripcion (usada para las alarmas)          |
| `CreateMonitoredItems`        | Asocia variables especificas a la suscripcion creada             |
| `Publish`                     | El SERVIDOR usa este service para empujar notificaciones de cambio al cliente, en cuanto ocurren |

## 4. Seguridad (o la falta de ella, en este laboratorio)

OPC UA, a diferencia de Modbus y DNP3 "clasicos", SI define un modelo de
seguridad robusto en el estandar: politicas de seguridad de transporte
(firma/cifrado con certificados X.509) y autenticacion de usuario
(anonima, usuario/clave, o certificado). Este laboratorio usa
deliberadamente **`SecurityPolicy = None`** y sesion anonima -- exactamente
la configuracion insegura que se ve en la practica cuando un integrador
deja las opciones de seguridad "por defecto" o las desactiva para
simplificar la puesta en marcha. La leccion aqui no es "OPC UA es
inseguro por diseno" (no lo es, tiene las piezas para ser seguro) sino
"un OPC UA mal configurado es tan inseguro como Modbus o DNP3sin
seguridad" -- que es, en la practica, muy comun.

## 5. Simplificaciones de este laboratorio

- Usamos la libreria `asyncua` (pura Python, activamente mantenida) en
  vez de escribir un codec a mano como en DNP3: OPC UA es un protocolo
  mucho mas grande y complejo (tipos, servicios, seguridad, discovery) y
  no tendria sentido reimplementarlo para este laboratorio.
- Sin seguridad de transporte ni autenticacion de usuario (ver seccion 4)
  -- a proposito, para que la comparacion con Modbus/DNP3 sea directa.
- Sin `Select-before-Operate`: los controles se escriben directo
  (equivalente a "Direct Operate" en terminologia DNP3), sin el paso
  intermedio de "reservar" el control antes de ejecutarlo.
- Un solo servidor, un solo namespace, sin discovery ni redundancia --
  fuera del alcance pedagogico de este laboratorio.

## 6. Abrir y filtrar `captures/opcua.pcap` en Wireshark

1. Copia el archivo desde el servidor: `scp usuario@servidor:.../opcua/captures/opcua.pcap .`
2. Abrelo con Wireshark. OPC UA usa el puerto TCP 4840; Wireshark lo
   decodifica automaticamente (columna *Protocol* dira `OpcUa`).
3. Filtro de pantalla recomendado: `opcua`.
4. Filtros utiles:
   - `opcua.ServiceNodeId contains "Read"` -> peticiones/respuestas de lectura.
   - `opcua.ServiceNodeId contains "Write"` -> peticiones/respuestas de escritura.
   - `opcua.ServiceNodeId contains "Publish"` -> notificaciones push de la suscripcion (el equivalente OPC UA a la UNSOLICITED_RESPONSE de DNP3).
   - `opcua.ServiceNodeId contains "CreateSubscription"` -> el momento exacto en que el master se suscribe a las alarmas.

## 7. Paso a paso: que deberia verse para cada accion

| # | Accion en el HMI                            | Que buscar en el pcap                                                                 |
|---|-----------------------------------------------|-------------------------------------------------------------------------------------------|
| 1 | Conexion inicial del `opcua-master`            | `CreateSession`, `ActivateSession`, varios `Browse`/`TranslateBrowsePathsToNodeIds` (busca las 4 zonas y sus 8 variables cada una), y un `CreateSubscription` + `CreateMonitoredItems` sobre las 8 variables de alarma |
| 2 | Polling automatico del SCADA                   | Un `Read` cada `POLL_SECONDS`, pidiendo el valor de varias variables a la vez            |
| 3 | Click **"Abrir"** en una zona                  | Dos `Write`: uno sobre `ModoManual` (valor `true`), otro sobre `Valvula` (valor `true`)  |
| 4 | Click **"Cerrar"**                             | Igual que (3) pero `Valvula` en `false`                                                   |
| 5 | Click **"Volver a Automatico"**                | Un `Write` sobre `ModoManual` (valor `false`)                                             |
| 6 | Cambiar un umbral                              | Un `Write` sobre `UmbralMinimo` o `UmbralMaximo` (valor Double)                            |
| 7 | Una alarma cambia de estado                    | Un mensaje `Publish` del SERVIDOR (no una respuesta a nada que el cliente haya pedido en ese momento) conteniendo una `MonitoredItemNotification` con el nuevo valor de la variable de alarma |

## 8. Como reconocer una notificacion de Subscription en el pcap

Busca mensajes `Publish` en el pcap. A diferencia de un `Read`, un
`Publish` del servidor:

- Llega en respuesta a un `PublishRequest` que el cliente **ya habia
  mandado antes**, potencialmente mucho antes -- OPC UA usa un patron de
  "long polling": el cliente manda un `PublishRequest` y el servidor NO
  responde de inmediato, lo deja pendiente hasta que hay algo que
  notificar (o vence un timeout). Esto es distinto tanto del polling
  Modbus (pregunta-respuesta inmediata) como de la unsolicited DNP3
  (mensaje verdaderamente espontaneo, sin ningun pedido pendiente).
- Contiene una o mas `MonitoredItemNotification`, cada una con el
  `ClientHandle` (identifica que variable suscrita cambio) y el nuevo
  valor.

Para el alumno, la forma mas facil de encontrarlo es: ubicar el momento
en que forzaste una alarma (ver Laboratorio 3), y buscar el primer
`Publish` que aparece justo despues -- deberia haber una diferencia de
milisegundos entre el cambio real de la variable en el servidor y la
notificacion que llega al cliente.
