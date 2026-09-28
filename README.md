# OT-MODBUS-DNP3-OPCUA-LAB

Laboratorio Docker de ciberseguridad OT/ICS: **un solo sitio web**, un
solo `docker-compose.yml`, **tres protocolos industriales** (Modbus TCP,
DNP3 y OPC UA) controlando el **mismo proceso fisico simulado** -- una
central de riego con 4 zonas (humedad, caudal, umbrales, valvula, modo
manual/automatico).

La idea pedagogica: comparar, sobre exactamente el mismo escenario, como
tres protocolos distintos resuelven lo mismo (lectura de sensores,
escritura de actuadores, aviso de alarmas) de forma diferente -- y sobre
todo, mostrar en la practica (con capturas de trafico reales, generadas
por el propio alumno) que ninguno de los tres trae autenticacion por
defecto.

Pensado para un curso de seguridad OT: cada protocolo trae su propia
documentacion, 3 guias de laboratorio que el alumno resuelve analizando
un `.pcap` que el mismo genera, y una pauta de correccion para el
docente.

## Tabla de contenidos

- [Requisitos](#requisitos)
- [Instalacion rapida (Linux)](#instalacion-rapida-linux)
- [Manual de instalacion detallado (Linux)](#manual-de-instalacion-detallado-linux)
- [Uso del sitio](#uso-del-sitio)
- [Protocolos incluidos](#protocolos-incluidos)
- [Acceso docente / Solucionario](#acceso-docente--solucionario)
- [Activar la captura de trafico (sniffing)](#activar-la-captura-de-trafico-sniffing)
- [Comandos utiles](#comandos-utiles)
- [Solucion de problemas comunes](#solucion-de-problemas-comunes)
- [Estructura del repositorio](#estructura-del-repositorio)
- [Licencia](#licencia)

## Requisitos

- Un equipo con **Linux** (Ubuntu/Debian/Kali funcionan igual de bien;
  cualquier distro con Docker Engine sirve).
- **Docker Engine** 24+ y el **plugin `docker compose`** (v2, el comando
  es `docker compose`, sin guion -- no `docker-compose`).
- `git` para clonar el repositorio.
- ~2 GB de espacio libre para las imagenes construidas, y los puertos
  **9090**, **5020**, **20000** y **4840** libres en el host (ver la
  tabla de [protocolos incluidos](#protocolos-incluidos)).
- Conexion a internet la primera vez (para descargar las imagenes base de
  Python y las dependencias de cada servicio).

No hace falta instalar Python, Modbus, DNP3 ni OPC UA en el host: todo
corre dentro de los contenedores.

## Instalacion rapida (Linux)

Para quien ya tiene Docker funcionando:

```bash
git clone https://github.com/H4ch1rou/OT-MOBUS-DNP3-OPCUA-LAB.git
cd OT-MOBUS-DNP3-OPCUA-LAB
docker compose up -d --build
```

Espera a que termine de construir (la primera vez tarda unos minutos:
compila las 3 imagenes de campo/SCADA, el HMI web, y descarga
`nicolaka/netshoot` para los sniffers). Abre luego:

```
http://localhost:9090
```

Si algo de esto falla, sigue el manual detallado de abajo -- cubre desde
instalar Docker hasta los errores mas comunes que aparecen la primera
vez que se levanta el laboratorio.

## Manual de instalacion detallado (Linux)

### 1. Instalar Docker Engine y el plugin Compose

Si ya tienes `docker compose version` funcionando, salta al paso 2.

**Ubuntu / Debian / Kali** (metodo recomendado, repositorio oficial de Docker):

```bash
# 1) dependencias y llave del repositorio oficial
sudo apt-get update
sudo apt-get install -y ca-certificates curl gnupg
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

# 2) agregar el repositorio (usa "debian" en vez de "ubuntu" si corresponde)
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
  https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# 3) instalar Docker Engine + el plugin Compose
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
```

Alternativa mas rapida (script oficial de conveniencia, cualquier distro compatible):

```bash
curl -fsSL https://get.docker.com | sudo sh
```

**Verificar la instalacion:**

```bash
docker --version
docker compose version
```

### 2. Correr Docker sin `sudo` (recomendado)

Por defecto, solo `root` (o alguien con `sudo`) puede hablarle al socket
de Docker. Para no tener que escribir `sudo` antes de cada comando:

```bash
sudo usermod -aG docker $USER
```

Cierra sesion y vuelve a entrar (o corre `newgrp docker` en la terminal
actual) para que el cambio tome efecto. Verifica con:

```bash
docker run hello-world
```

Si prefieres no hacer esto, simplemente antepone `sudo` a todos los
comandos `docker`/`docker compose` de esta guia.

### 3. Clonar el repositorio

```bash
git clone https://github.com/H4ch1rou/OT-MOBUS-DNP3-OPCUA-LAB.git
cd OT-MOBUS-DNP3-OPCUA-LAB
```

### 4. Levantar el laboratorio completo

Desde la raiz del repositorio:

```bash
docker compose up -d --build
```

- `-d` (detached): todo corre en segundo plano, no necesitas dejar
  ninguna terminal abierta.
- `--build`: fuerza a construir las imagenes locales (necesario la
  primera vez, y cada vez que el codigo cambie).

Esto levanta **13 contenedores**: por cada protocolo (Modbus, DNP3, OPC
UA) un servicio "de campo" (RTU/outstation/servidor), un SCADA
("master"), un punto de captura de trafico (inactivo hasta que lo
actives), y una consola de operador (no arranca sola, se invoca a
demanda) -- mas el dashboard web unificado.

### 5. Verificar que todo quedo arriba

```bash
docker compose ps
```

Deberias ver `modbus-slave`, `modbus-master`, `dnp3-outstation`,
`dnp3-master`, `opcua-server`, `opcua-master` y `webhmi` en estado
`running` (los `*-sniffer` tambien apareceran corriendo, pero inactivos
hasta que entres a activarlos; los `*-operador` no apareceran en este
listado porque no arrancan con `up`).

Si algo no quedo `running`, revisa sus logs:

```bash
docker compose logs <nombre-del-servicio>
```

### 6. Abrir el dashboard

```
http://localhost:9090
```

Desde cualquier navegador del mismo equipo (o de otro equipo en la misma
red, cambiando `localhost` por la IP del servidor).

## Uso del sitio

La pagina de inicio presenta los tres protocolos. El **menu lateral**
(presente en todas las paginas) permite moverte entre:

- El **Dashboard** de cada protocolo: panel de control tipo SCADA con
  las 4 zonas de riego, donde puedes abrir/cerrar valvulas, cambiar
  umbrales de humedad, y ver alarmas en vivo.
- La **Documentacion** de cada protocolo: como funciona el laboratorio,
  y una guia del protocolo en si (estructura de mensajes, como leerlos
  en Wireshark).
- Los **Laboratorios**: 3 guias por protocolo que se resuelven
  analizando una captura de trafico generada por el propio alumno.
- El **Solucionario** (con candado 🔒): la pauta de correccion, protegida
  con login docente (ver la seccion siguiente).

Cada seccion del menu es expandible/colapsable (click en el nombre del
protocolo), y la navegacion entre paginas es instantanea -- no recarga
el sitio completo (aunque cada pagina tambien funciona perfectamente si
se accede en forma directa, por ejemplo desde `curl` o sin JavaScript).

## Protocolos incluidos

| Protocolo   | Dashboard                        | Puerto publicado | Rol de "campo"         | Rol de "control"  |
|-------------|-------------------------------------|--------------------|---------------------------|----------------------|
| Modbus TCP  | `http://localhost:9090/modbus/`     | `5020` (Modbus)     | `modbus-slave`             | `modbus-master`      |
| DNP3        | `http://localhost:9090/dnp3/`       | `20000` (DNP3)      | `dnp3-outstation`          | `dnp3-master`        |
| OPC UA      | `http://localhost:9090/opcua/`      | `4840` (OPC UA)     | `opcua-server`             | `opcua-master`       |

El dashboard web (puerto **9090**) es un unico sitio Flask que le habla a
los tres protocolos por debajo. Documentacion especifica de cada uno:

- [`modbus/README.md`](modbus/README.md) y [`modbus/PROTOCOLO-MODBUS.md`](modbus/PROTOCOLO-MODBUS.md)
- [`dnp3/README.md`](dnp3/README.md) y [`dnp3/PROTOCOLO-DNP3.md`](dnp3/PROTOCOLO-DNP3.md)
- [`opcua/README.md`](opcua/README.md) y [`opcua/PROTOCOLO-OPCUA.md`](opcua/PROTOCOLO-OPCUA.md)

## Acceso docente / Solucionario

Cada protocolo tiene, ademas de sus 3 guias de laboratorio, una **pauta
de correccion** (`laboratorios/pauta-docente.md`) con el resultado
esperado y el paso a paso de resolucion. Se accede desde el dashboard,
seccion **"Solucionario 🔒"** del menu lateral, pero exige iniciar sesion
como docente primero (link "🔒 Acceso docente" al pie del menu).

Usuario y clave por defecto (configurados en `docker-compose.yml`,
variables de entorno del servicio `webhmi`):

```yaml
SOLUCIONARIO_USUARIO: "docente"
SOLUCIONARIO_PASSWORD: "riego2024"
SECRET_KEY: "agroriego-cambia-esta-clave-secreta"
```

> ⚠️ **Cambia estas tres variables antes de usar el laboratorio con
> alumnos reales.** Vienen con un valor por defecto solo para que el
> laboratorio funcione "out of the box" al clonarlo; no son credenciales
> pensadas para produccion. Edita `docker-compose.yml` (o usa un archivo
> `.env`, que este repositorio ignora vía `.gitignore`) y vuelve a
> levantar el servicio `webhmi`:
>
> ```bash
> docker compose up -d --build webhmi
> ```

## Activar la captura de trafico (sniffing)

Cada protocolo trae su propio contenedor `<protocolo>-sniffer`
(`modbus-sniffer`, `dnp3-sniffer`, `opcua-sniffer`), que comparte el
namespace de red del servicio de campo correspondiente -- ve exactamente
el mismo trafico que le llega al RTU/outstation/servidor. **A proposito,
ninguno captura nada por si solo**: hay que entrar y activarlo a mano,
para que sea una accion consciente del alumno, no un detalle que quede
corriendo de fondo sin que se note.

```bash
docker exec -it modbus-sniffer sh      # o dnp3-sniffer / opcua-sniffer
tcpdump -i any -n -A 'tcp port 502'    # 502=Modbus, 20000=DNP3, 4840=OPC UA
```

Para guardar la captura y analizarla despues con Wireshark (queda en el
host, en `<protocolo>/captures/<protocolo>.pcap`):

```bash
tcpdump -i any -n -w /captures/modbus.pcap 'tcp port 502'
```

El detalle completo, con el paso a paso de cada laboratorio y que
deberia verse en el pcap para cada accion, esta en el
`PROTOCOLO-<NOMBRE>.md` y en `laboratorios/` de cada carpeta de
protocolo.

## Comandos utiles

```bash
docker compose ps                        # que esta corriendo
docker compose logs -f webhmi            # seguir los logs del dashboard
docker compose logs -f modbus-master     # ver el lazo de control de un SCADA
docker compose restart opcua-master      # reiniciar un servicio puntual
docker compose run --rm dnp3-operador    # consola de operador manual (DNP3)
docker compose down                      # detener y limpiar todo
```

Las consolas de operador disponibles son `modbus-operador`,
`dnp3-operador` y `opcua-operador` -- ninguna arranca con `up` porque son
interactivas; se invocan con `docker compose run --rm <nombre>`.

## Solucion de problemas comunes

**`Pool overlaps with other one on this address space` al hacer `up`**
El pool de direcciones por defecto de Docker puede quedar agotado en
hosts con muchas redes acumuladas (o VPNs activas). Este repositorio ya
fija una subred explicita en `docker-compose.yml` para evitarlo, pero si
igual aparece:

```bash
docker network ls                # ver cuantas redes hay acumuladas
docker network prune -f          # liberar las que no esten en uso (seguro)
docker compose up -d --build     # reintentar
```

**`permission denied` al hablar con `/var/run/docker.sock`**
Tu usuario no esta en el grupo `docker` -- ver el paso 2 del manual de
instalacion (`sudo usermod -aG docker $USER`, luego cerrar sesion).
Mientras tanto, antepone `sudo` a los comandos.

**Un dashboard muestra "sin conexion" o las zonas no cargan**
El servicio de campo correspondiente puede no haber terminado de
arrancar todavia. Espera unos segundos y revisa:

```bash
docker compose logs modbus-slave     # o dnp3-outstation / opcua-server
```

**Cambie un archivo `.py` y no se reflejan los cambios**
Los servicios de codigo Python (a diferencia de los `.md` de
documentacion) se copian dentro de la imagen en el build. Despues de
editar codigo, hay que reconstruir:

```bash
docker compose up -d --build <servicio>
```

**Los puertos 9090/5020/20000/4840 ya estan en uso**
Edita el lado izquierdo de cada mapeo de puertos en `docker-compose.yml`
(por ejemplo `"9091:8080"` en vez de `"9090:8080"`) y vuelve a levantar.

**Una valvula abierta a mano "se cierra sola" a los pocos segundos**
No es un bug: es el SCADA automatico peleando por el mismo actuador con
tu cambio manual. Cada protocolo resuelve esto con un flag de "modo
manual" por zona -- ver la seccion "Modo Manual vs. Automatico" en
[`modbus/README.md`](modbus/README.md) para el detalle completo (aplica
igual, con su propia implementacion, a los tres protocolos).

## Estructura del repositorio

```
OT-MOBUS-DNP3-OPCUA-LAB/
  docker-compose.yml     <- unico compose: levanta los 13 contenedores
  webhmi/                <- dashboard web unificado (Flask), un solo puerto
  modbus/                <- RTU (slave), SCADA (master), operador de consola
  dnp3/                  <- outstation, SCADA (master), operador, codec DNP3 propio
  opcua/                 <- servidor, SCADA (master), operador
```

Cada carpeta de protocolo trae, ademas del codigo de sus servicios:

- `README.md`: como funciona ese laboratorio en detalle.
- `PROTOCOLO-<NOMBRE>.md`: explica el protocolo en si y como leer su
  captura de trafico en Wireshark.
- `laboratorios/`: 3 guias que los alumnos resuelven analizando un
  `.pcap` que ellos mismos generan, mas `pauta-docente.md` (expuesta en
  el dashboard bajo login docente, ver [Acceso docente](#acceso-docente--solucionario)).
- `captures/`: donde quedan los `.pcap` generados por cada sniffer (no
  versionados en git, ver `.gitignore`).

### Convenciones comunes a los tres protocolos

- **Un solo `docker-compose.yml`**, en la raiz. Los tres protocolos (mas
  el dashboard web) se levantan y se bajan juntos, en una unica red
  Docker.
- Los servicios "de campo" y "de control" arrancan siempre en segundo
  plano (`docker compose up -d`); las consolas de operador se invocan a
  demanda.
- La captura de trafico nunca arranca capturando por si sola: el alumno
  debe activarla manualmente (ver [Activar la captura de
  trafico](#activar-la-captura-de-trafico-sniffing)).
- La documentacion (`README.md`, `PROTOCOLO-*.md`, `laboratorios/*.md` de
  cada carpeta) se monta como archivos de solo lectura dentro del
  contenedor `webhmi`, y se sirve convertida a HTML en el dashboard:
  cualquier edicion a esos `.md` se refleja ahi sin reconstruir la
  imagen.
- Los tres protocolos comparten exactamente el mismo modelo de zonas de
  riego (Parronal, Hortalizas, Frutales, Vivero) y el mismo mecanismo de
  "modo manual vs. automatico" para evitar que el SCADA sobreescriba un
  cambio manual -- implementado de forma distinta en cada protocolo (una
  coil extra en Modbus, un punto Binary Output en DNP3, una variable
  booleana en OPC UA), pero con la misma logica de fondo.

## Licencia

Este proyecto se distribuye bajo la licencia [Apache 2.0](LICENSE).
