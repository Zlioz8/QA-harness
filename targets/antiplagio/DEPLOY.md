# Despliegue — Antiplagio

Módulo Antiplagio de Zajuna: **plugin Moodle (PHP) + API FastAPI + producer + 3 analyzers
Python sobre Kafka**. Cuatro piezas en un repo, y el error más caro es creer que desplegar el
plugin despliega el módulo: **no**. La casilla la pinta el plugin, pero quien analiza es el
analyzer, en un contenedor aparte.

> **Estado a 2026-08-31.** Local: funciona, 18/18 verificaciones en verde. **Preproducción: toda
> actividad nueva falla** (`hallazgos/H8.md`), causa sin confirmar por falta de SSH. Las tres
> evidencias de la demo funcionan porque se analizaron antes.

## Las cuatro piezas y qué aporta cada una

| Pieza | Dónde vive | Si falta o está vieja |
|---|---|---|
| Plugin `local_antiplagiarsena` | `/var/www/zajuna/local/antiplagiarsena` | 404 en los endpoints nuevos; la casilla no aparece |
| API FastAPI | servicio `api-antiplagio` (:8030) | El botón Analizar no encola nada |
| Producer | servicio `antiplagio-producer` | El mensaje no llega a Kafka |
| **Analyzers `app0/1/2`** | contenedores Docker | **El análisis falla o termina sin cotejo web** |

`docker-compose.yml:69` — los tres analyzers leen `env_file: .env`, es decir
`antiplagio/docker_config/.env`. **No** leen `antiplagio_web_backend/docker_config/.env`, que es
del flujo web viejo. Ahí está el origen probable de H8.

## 0. Antes de nada — variables del analyzer

En `antiplagio/docker_config/.env` (el del analyzer, no otro):

```
# Cotejo contra internet. Sin WINSTON_TOKEN, enabled() es False y NUNCA se llama a Winston:
# el análisis termina en verde y sin fuentes rojas, indistinguible de "nadie copió de internet".
WEB_CHECK=1
WINSTON_TOKEN=<ver target.env.local — PENDIENTE DE ROTAR>
WINSTON_BASE_URL=https://api.gowinston.ai
WINSTON_PLAGIARISM_PATH=/v2/plagiarism
WINSTON_MAX_CHARS=12000
WEB_PARA_MIN_OVERLAP=0.35

# Secreto compartido analyzer <-> API para /process/status. DEBE ser el MISMO en
# api_antiplagio/.env y en docker_config/.env. Puesto en un solo lado, cada análisis
# muere en 401 sin decir por qué. Vacío = sin autenticación (solo dev).
PROCESS_STATUS_SECRET=<openssl rand -hex 24>
```

> `WEB_CHECK` sin definir equivale a **encendido** (`os.getenv("WEB_CHECK","1")`). Lo que apaga
> de verdad es que falte `WINSTON_TOKEN`: `enabled()` exige las dos cosas.

> **Coste de Winston: 2,00 créditos por palabra**, medido, no estimado. Y se cobra por **todos**
> los ficheros de la actividad, no solo el aprendiz objetivo (`instructor_component.py:606`).
> Marcar la casilla en EV-A (13 documentos) son ~9.900 créditos.

## 1. Local (bare metal, la referencia)

El plugin es un **bind mount** del repo, así que lo que corre *es* la rama `dev`:

```
/home/zlioz/proyectos/antiplagio/antiplagio/plugin/antiplagiarsena
  → /var/www/zajuna/local/antiplagiarsena          (línea en /etc/fstab)
```

Los analyzers se construyen desde `/home/zlioz/proyectos/antiplagio/antiplagio/docker_config`.

```bash
# Verificación completa: 18 comprobaciones (bind mount, servicios, contenedores,
# endpoints, BD, trigger, versión del plugin sincronizada disco=BD).
escenario/../entorno-local/verificar-entorno.sh
```

Instalación desde cero: `entorno-local/manual_instalacion_local_20260818.md`.

> **`opcache.validate_timestamps=0`** en local (`/etc/php/8.1/fpm/conf.d/99-zajuna.ini`): editar
> un `.php` y recargar el navegador **no cambia nada**, sin ningún aviso. Hace falta
> `sudo systemctl reload php8.1-fpm`.

## 2. Preproducción

Destino de despliegue: rama **`dev`**, directamente. `mq5preproduccion` quedó descartada.

Subir a `dev` no despliega: hay que ejecutar después los pasos de despliegue (rsync,
`upgrade.php`, `purge_caches.php`, recargar PHP-FPM). Procedimiento completo y las trampas
encontradas: **`RECUPERACION-PREPROD.md`**.

Del lado de servicios, el despliegue histórico se hizo con un *worktree* y rsync selectivo:

```bash
cd /opt/antiplagio && git fetch origin dev
git worktree add /opt/antiplagio-dev origin/dev
rsync -a --exclude '.env' --exclude '__pycache__' /opt/antiplagio-dev/antiplagio/analyzer_plagiarism/ /opt/antiplagio/antiplagio/analyzer_plagiarism/
# ... ídem api_antiplagio, antiplagiarism_producer, docker_config
sudo systemctl restart api-antiplagio antiplagio-producer
cd /opt/antiplagio/antiplagio/docker_config && docker compose up -d --build app0 app1 app2
```

> **Ese `--exclude '.env'` es probablemente la causa de H8.** Protege los `.env` en marcha, pero
> también impide que lleguen variables nuevas (como las de Winston). Al añadir variables al
> despliegue hay que ponerlas **a mano** en el servidor: el rsync no las va a llevar nunca.

### Sin `sudo -u www-data php`

En preprod no hay CLI de Moodle. Todo cambio de escenario debe poder hacerse por interfaz:
**`escenario/PASOS-UI-PREPROD.md`**. Dos restricciones que cuestan tiempo si no se saben:

- El **admin** puede crear actividades y sembrar entregas, pero **no puede analizar**
  (`is_siteadmin` en `index.php`).
- El **instructor** puede analizar, pero **no puede sembrar** (`error/nopermission`).
- Son dos sesiones distintas, obligatoriamente.
- El login es el portal `https://zajunavideo5.com/`, pestaña *"Ingreso Administrativos Zajuna"*.
  `/zajuna/login/index.php` rebota a `caplms.sena.edu.co`.

## 2.b El analyzer pasa a correr sin privilegios · **paso obligatorio de migración**

Desde `fix/auditoria-sensibilidad-2026-08`, el `Dockerfile` del analyzer declara `USER appuser`
(UID 1000). El motivo está en `hallazgos/triaje-sast-y-config.md`: ese contenedor abre los
ficheros que suben los aprendices con librerías de parseo que arrastran CVE.

**Antes de desplegarlo hay que arreglar los permisos en el host, o el analyzer no arranca.**

```bash
# Los logs existentes pertenecen a root: los creó el contenedor anterior corriendo como root.
# OJO a la ruta: es la que MONTA docker-compose, que puede no ser la del checkout.
# En local, /opt/antiplagio es un bind mount del repo (mismo inodo), y es la ruta montada:
sudo chown -R 1000:1000 /opt/antiplagio/antiplagio/analyzer_plagiarism/logs/

# Comprobar cuál es en cada máquina, en vez de suponerlo:
#   docker inspect app0 --format '{{range .Mounts}}{{.Source}} -> {{.Destination}}{{println}}{{end}}'
```

**Reconstruir los tres a la vez, no de uno en uno.** Si `app1`/`app2` siguen corriendo como root
mientras `app0` ya es `appuser`, los que aún son root **recrean `backend.log` como root** al
rotarlo, y vuelven a dejar fuera al que no lo es. Pasó durante la validación: `app0` arrancó
bien, y al reconstruir los otros dos el fichero era otra vez de root.

Sin eso, el arranque muere con:

```
PermissionError: [Errno 13] Permission denied: '/app/logs/backend.log'
```

y el contenedor entra en bucle de reinicio. El `chown -R` del Dockerfile **no lo cubre**: ese
directorio es un volumen montado del host, que se superpone a lo que traiga la imagen.

> Esto es exactamente lo que hizo fracasar el intento anterior: el `USER` llevaba comentado
> desde el principio, junto a un `chown` con una errata (`noonrootuser`). Se desactivó en vez de
> corregirse, y el porqué no quedó escrito en ninguna parte.

Comprobar además que los otros dos volúmenes son escribibles por el UID 1000
(`/opt/compressed_reports`, `.../antiplagio/files`). En local son `777`.

**Verificado en local el 2026-08-31**: con el `chown` hecho, `app0` reconstruido procesó un
análisis completo (`id_process=272`) — reporte, PDF, ZIP y persistencia — sin un solo error de
permisos.

> `app1` y `app2` siguen con la imagen anterior: se reconstruyen igual
> (`docker compose up -d --build app0 app1 app2`), con el mismo `chown` hecho antes.

## 3. Comprobación de que el despliegue quedó bien

Hoy **no existe** y es justo lo que faltó: H8 se detectó tres semanas tarde. Lo mínimo que
debería comprobar, contra una línea base conocida:

```bash
# 1. ¿El analyzer trae el refactor?
docker exec app0 ls -l /app/components/instructor/web_match.py

# 2. ¿Tiene las variables? (enmascarando el token)
docker exec app0 printenv | grep -E 'WEB_CHECK|WINSTON_' | sed 's/\(TOKEN=..\).*/\1…/'

# 3. ¿El código coincide con dev?
docker exec app0 md5sum /app/components/instructor/instructor_component.py

# 4. Versión del plugin: disco == BD
# 5. Umbrales en local_adminantiplag_perfiles: 0.13 y 0.15
# 6. Los porcentajes del escenario coinciden con la línea base
```

Los puntos 3 y 6 **necesitan una línea base congelada**, y hoy no la hay: ver
`hallazgos/orden.md` §1. Es el paso siguiente inmediato.

## 4. Escenario de demo

Scripts en `escenario/cli/`, corpus en `escenario/corpus/`, binarios en `escenario/build/`:

```bash
sudo -u www-data php 02_evidencias.php --run        # EV-A, EV-B, EV-C
sudo -u www-data php 07_evidencia_web.php --run     # EV-W (cotejo internet)
sudo -u www-data php 03_flags_y_roles.php --run
sudo -u www-data php 05_sembrar.php --run           # todas, o --solo=EV-W
```

> **Analizar EV-C ANTES que EV-A.** El almacén de firmas nace vacío; si EV-A va primero, no hay
> firma del donante contra la que cruzar y el caso grave sale sin fuente externa.

Guion de la demo y resultados esperados: `escenario/guion/` y `escenario/README.md`.
