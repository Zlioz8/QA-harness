# Presupuesto del hilo principal — `main-thread-budget.spec.ts`

**Dimensión:** `[live]` · **Se hereda:** sí, todo perfil la corre con `make e2e` · **Target propio:** `make budget`

## Qué agujero tapa

Costos Web R8 §3.22: la aplicación «se pegaba» y **ningún instrumento del laboratorio lo veía**.
k6 medía el servidor y lo encontraba ocioso (php-fpm al 0 %, la API en 27 ms); ZAP medía cabeceras;
la matriz de autorización medía permisos. El trabajo caro ocurría **dentro del navegador**: 18 MB de
imágenes que en realidad eran mapas de bits incrustados en un envoltorio SVG, descodificados y
rasterizados en el hilo principal. El laboratorio entero medía el lado del servidor; nadie medía el
lado del usuario, que es donde se sufría el defecto.

## Por qué anticipa en vez de describir

Tres decisiones, y las tres nacieron de errores reales cometidos durante la investigación de §3.22:

1. **Rastrea el bundle entero, no la pantalla actual.** Sigue de forma transitiva los chunks de Vite
   —incluidas las rutas relativas `./Pantalla-hash.js`, que es donde viven las pantallas internas— y
   contabiliza toda imagen referenciada. La pantalla de acceso nunca descarga el icono de 3 MB del
   gestor de guías; el usuario lo paga tres pantallas después. Medido solo en la portada, el
   despliegue roto daba **7 imágenes / 2,1 MB**; con el rastreo transitivo da **58 imágenes / 17,9 MB**.

2. **Cuenta megapíxeles descodificados, no bytes.** Es la magnitud que predice el bloqueo. Un PNG de
   200 KB y 4000×3000 ocupa 48 MB de mapa de bits y cuesta lo mismo descodificar esté comprimido como
   esté. El primer intento de corrección de §3.22 recomprimió sin redimensionar: los bytes bajaron un
   67 % y **los megapíxeles no se movieron ni uno**. Un presupuesto en bytes habría dado el visto bueno
   a una corrección que no corregía.

3. **Mide con la CPU frenada** (`Emulation.setCPUThrottlingRate`, por defecto ×4). En la máquina del
   equipo de desarrollo nada se congela nunca; el defecto aparece en el portátil del funcionario. El
   frenado convierte «a mí me funciona» en un número reproducible.

## Presupuestos

Se declaran en `targets/<perfil>/target.env`. Los valores por defecto son deliberadamente laxos: esta
spec debe delatar catástrofes, no imponer una dieta a proyectos sanos.

| Variable | Def. | Qué acota |
|---|---|---|
| `PERF_IMG_TOTAL_KB` | 2048 | peso sumado de las imágenes del bundle |
| `PERF_IMG_MAX_KB` | 300 | peso de la imagen más pesada |
| `PERF_IMG_MAX_MPX` | 8 | megapíxeles descodificados (×4 = MB de RAM de mapa de bits) |
| `PERF_TBT_MS` | 600 | tiempo total de bloqueo durante la carga |
| `PERF_LONGTASK_MS` | 250 | peor tarea larga individual |
| `PERF_CPU_THROTTLE` | 4 | factor de frenado de CPU |
| `PERF_BUDGET_PATH` | `/` | ruta a medir |
| `PERF_BUDGET_SKIP` | — | `1` en un target sin frontend |

## Validación de la propia herramienta

Contrastada contra los dos extremos del mismo proyecto, mismo código, solo cambian las imágenes:

| | Costos Web `f3d4758e` (roto) | Costos Web `ed65338a` (corregido) |
|---|---|---|
| Imágenes descubiertas | 58 | 55 |
| Peso total | **17.928 KB** | 567 KB |
| Megapíxeles | **18,2 MPx (73 MB RAM)** | 5,1 MPx (20 MB RAM) |
| Veredicto | **2 pruebas en rojo** | 5 en verde |

Que falle donde debía fallar y pase donde debía pasar es el requisito mínimo para que un instrumento
nuevo entre al laboratorio: una spec que solo pasa no demuestra nada.

## Uso

```bash
make budget TARGET=costos_web     # solo el presupuesto
make e2e    TARGET=costos_web     # la suite completa, esta spec incluida
```

## Límites conocidos

- Mide la **ruta de entrada** (`PERF_BUDGET_PATH`). El descubrimiento de imágenes sí cubre el bundle
  completo, pero las tareas largas se observan solo durante esa carga. Para medir el bloqueo de una
  pantalla interna concreta hay que apuntar `PERF_BUDGET_PATH` a ella con sesión iniciada.
- `longtask` no existe en Firefox ni en WebKit: contra esos navegadores la spec degrada a presupuesto
  de imagen y megapíxeles, que es la parte anticipatoria y la que de verdad importa.
- No juzga calidad visual. Redimensionar de más se detecta a ojo, no aquí.
