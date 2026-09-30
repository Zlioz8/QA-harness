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

`sobre.sh` acepta `SOBRE_CPUS`, `SOBRE_MEM`, `SOBRE_WORKERS`, `SOBRE_LOG_LEVEL`. Lo que quedó
puesto se lee del contenedor con `sobre.sh ver`, no de este archivo.

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
