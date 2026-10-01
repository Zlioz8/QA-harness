# Carga y capacidad de Zajuna Móvil — cómo se corre

Todo desde la raíz de SECURITY-LAB. Solo contra el despliegue **LOCAL**: siembra usuarios en
Moodle y cambia cómo confía la API en la IP del cliente. Contra preprod, ver el final.

## 1. Preparar (una vez por sesión de medida)

```bash
# 1.000 personas sintéticas en el Moodle local (8 min). La clave nace aquí y solo va a k6/datos/.
sudo -u www-data php targets/movil/carga/sembrar-usuarios.php --moodle=/var/www/zajuna \
     --count=1000 --fondo=40 --por-curso=25 --referencia=23542 > targets/movil/k6/datos/cuentas.json
chmod 600 targets/movil/k6/datos/cuentas.json

targets/movil/carga/silencio.sh poner     # para lo ajeno a la prueba y apunta qué paró
targets/movil/carga/sobre.sh poner        # la API con límites declarados y un salto de proxy más
```

`sobre.sh` acepta `SOBRE_CPUS`, `SOBRE_MEM`, `SOBRE_WORKERS`, `SOBRE_LOG_LEVEL`, y dos interruptores para medir un
cambio por partes: `SOBRE_REDIS_URL=` (vacío: la API sin estado compartido) y `SOBRE_COLAPSO=0` (sin candado entre procesos). Lo que quedó
puesto se lee del contenedor con `sobre.sh ver`, no de este archivo. **Los techos van con el
sobre:** `PERF_TECHOS` del `target.env` declara `cpu=100` por proceso uvicorn y `conexiones=30` por
proceso en la base de la API; con `SOBRE_WORKERS=2` son 200 y 60 (L-R9-07: una escalera juzgada con
los techos de un proceso atribuyó el cuello a la base cuando era php-fpm).

## 2. Medir

```bash
make perf TARGET=movil                                  # humo: una persona, un login
make perf-escalera TARGET=movil ESCALERA=imposible      # control negativo: debe parar en el paso 1
make perf-escalera TARGET=movil ESCALERA=humo           # dos pasos cortos: ¿funciona el instrumento?
CARGA_ITER=12 make perf-escalera TARGET=movil ESCALERA=linea-base   # costo de cada gesto, sin compañía
ESCALERA_NOTA="qué sobre es este" make perf-escalera TARGET=movil   # la escalera de verdad
make capacidad TARGET=movil                             # CAPACIDAD.md de la última
tools/perf-capacidad.py comparar reports/movil/k6/runs/<A> reports/movil/k6/runs/<B> --nombres antes,despues
```

Otras formas, con el mismo modelo:

```bash
make perf-escalera TARGET=movil ESCALERA=pico-login     # todos inician sesión a la vez
make perf-escalera TARGET=movil ESCALERA=aula           # 40 personas detrás de una sola IP
make perf-escalera TARGET=movil ESCALERA=resistencia    # dos horas a carga media
```

## 2b. El teléfono real, de extremo a extremo

La app del destino `local` escribe en la consola del WebView una línea por petición al salir y otra
al volver (`[trace] <rid> fin <ms> <estado> <ms_servidor>`, `movil/src/main.ts`). `telefono.sh` la
lee por CDP mientras conduce los gestos del modelo en el DOM real, y deja por petición: tiempo en el
teléfono, tiempo del servidor (`X-Execution-Time-Ms`) y, por diferencia, la red.

```bash
export ANDROID_SERIAL=<serie>                            # con ADB inalámbrico el mismo teléfono sale dos veces
targets/movil/carga/telefono.sh reports/movil/telefono/<fecha>/reposo   # servidor libre, 3 vueltas
targets/movil/carga/telefono-bajo-carga.sh 1proc "100 200"              # la escalera en segundo plano y el teléfono en cada meseta
python3 targets/movil/carga/telefono-resumen.py reports/movil/telefono/<fecha>   # la tabla: qué sintió la persona
```

El teléfono tiene que estar en la red desde la que se alcanza `BASE_URL` (el hotspot del equipo de pruebas), con la app `io.ionic.starter.local`
instalada y `WEBVIEW_DEBUG=true` (destino `local`). La cuenta es la de aprendiz del perfil (ROLE_B).

## 2c. La animación

```bash
TELEFONO=reports/movil/telefono/<fecha>/reposo targets/movil/carga/animacion-armar.sh reports/movil/animacion/animacion.html \
  "reports/movil/k6/runs/<corrida>/00200vus:1 proceso · 200 personas" "…"
```

Para ver **qué cambió** entre dos corridas del mismo escenario, se pasan las dos con la misma etiqueta
y el lado tras una barra; la animación las empareja y las dibuja a la vez, con el mismo reloj:

```bash
PROCESOS=2 EXTRAS=reports/movil/animacion/antes-despues-extras.json targets/movil/carga/animacion-armar.sh reports/movil/animacion/animacion-antes-despues.html \
  "reports/movil/k6/runs/<antes>/00200vus:Aula de 200 personas detrás de una IP|antes" \
  "reports/movil/k6/runs/<después>/00200vus:Aula de 200 personas detrás de una IP|despues"
```

Es **una sola animación** por perfil: el «antes» es la primera medición y no se toca; cuando el código
cambia, se rearma apuntando el «después» a la corrida nueva. Sin niveles intermedios.

En ese modo se ven moverse las respuestas 429 (rebotan en nginx), las filas hacia la base de la API y
las líneas de log por segundo. `EXTRAS` es un JSON `[{medida, antes, despues, fuente}]` con lo medido
fuera de esas corridas; sale en una tabla bajo el lienzo. `PROCESOS` son los procesos uvicorn del sobre.

`animacion.html` es un solo archivo: se abre en cualquier navegador. Cada número sale de los logs y la
telemetría de la corrida (`animacion-datos.py`); lo único dibujado es la posición de cada paquete dentro
de su segundo.

## 3. Restaurar

```bash
targets/movil/carga/sobre.sh quitar
targets/movil/carga/silencio.sh quitar
sudo -u www-data php targets/movil/carga/sembrar-usuarios.php --moodle=/var/www/zajuna --delete
```

## Qué hay en esta carpeta

| Archivo | Qué es |
|---|---|
| `grabacion.py` | extrae el tráfico real de la app de los logs del proxy y del backend y lo casa por `rid`. De ahí sale `k6/modelo.js` |
| `grabacion/<fecha>/` | lo extraído (no se versiona): `RESUMEN.md`, `rutas.csv`, `rafagas.csv` |
| `sembrar-usuarios.php` | las personas sintéticas: crea, cuenta y borra |
| `sobre.compose.yml`, `sobre.sh` | el sobre de la prueba, como override del compose de `movil_api` |
| `silencio.sh` | para y devuelve lo que no es parte de la prueba |
| `*.env` | las escaleras |
| `hook-antes.sh`, `hook-despues.sh`, `tablas.sh` | lo que la API escribe en su base por petición, y las llamadas a Moodle por ruta |
| `demanda.json` | los escenarios de demanda, cada uno con su fuente |
| `telefono.sh`, `telefono.js`, `telefono-bajo-carga.sh`, `telefono-resumen.py` | el teléfono real como instrumento: recorridos por CDP y cada petición vista desde el teléfono |
| `animacion-datos.py`, `animacion.html`, `animacion-armar.sh` | la animación de cómo se acumulan los retrasos, armada con los registros de una corrida |

## Rehacer el modelo cuando cambie la app

```bash
python3 targets/movil/carga/grabacion.py extraer  targets/movil/carga/grabacion/$(date +%Y%m%d)
python3 targets/movil/carga/grabacion.py analizar targets/movil/carga/grabacion/$(date +%Y%m%d) --ua Dalvik
```

`--ua Dalvik` deja solo lo que pidieron los teléfonos. Las ráfagas de `RESUMEN.md` son los gestos
de `k6/modelo.js`: si una cambia, cambia el gesto y el comentario que cita cuántas veces se midió.
Después, fidelidad: correr `linea-base` y comparar su `grab/RESUMEN.md` con el de la grabación.

## Contra preprod

No se siembra nada ni se cambia el sobre. Solo con el visto bueno de quien responde por ese
servidor, con tope de usuarios y corte automático:

```bash
ESCALERA_ABORTA=1 make perf-escalera TARGET=movil ESCALERA=preprod
```

con `BASE_URL`/`APP_INTERNAL_URL` y las dos cuentas de preprod en `target.env.local`. Todas las
peticiones salen de una IP: los 429 que aparezcan son el límite por IP, y se leen así.
