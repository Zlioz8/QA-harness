Todo el código es de **Johan Sebastián Valle** (`feature/v2`). El orden es por impacto, no por
persona:

**1. Entregar el esquema de la BD `integracion` (P3, Alta).** Es la pieza que rompe la
reproducibilidad: sin ella, los Resultados de Aprendizaje no funcionan en ningún despliegue nuevo, y
el propio manual reconoce no poder documentarla. Versionar un `install.sql` con las tablas y vistas
que `IntegracionResultadosService` consulta (el esquema, no los datos reales) más un procedimiento
de sincronización. Con eso cualquiera reconstruye el entorno.

**2. Quitar la credencial por defecto postgres/12345 (P1, Alta).** En `settings.php`, dejar el
default de la contraseña VACÍO (que el plugin falle con un mensaje claro si no está configurada) y,
en `IntegracionDbConnection`, no caer a `postgres`. La conexión de solo lectura debe usar un rol de
solo lectura, como el que esta auditoría creó (`portafolio_integ_ro`). Rotar el `12345` si ya se
desplegó en algún sitio.

**3. Alinear el DEPLOY.md con el ambiente de destino (P6, Media).** El manual describe la máquina del
autor (Apache/HTTP/5433); el destino es nginx/HTTPS/5432 bajo `/zajuna`. Parametrizarlo o reescribirlo
contra el ambiente de integración real, y arreglar el smoke test §16.1 que fija `Server: Apache`.

**4. No mostrar «0 resultados» cuando la BD falla (P2, Media).** En los dos `catch (\dml_exception)`
de `IntegracionResultadosService` (líneas 138 y 317), registrar el error y hacer que la vista
distinga «sin resultados» de «no se pudieron cargar». Una línea de log y un mensaje.

**5. Desplegar sin `.git` en el webroot (P5, Media).** Cambiar el §4.3 del manual de `git clone` a
copiar el árbol sin `.git` (o `git archive`). Y pedir al dueño del core que arregle la regla `deny`
del nginx para bloquear `/\.git(/|$)` — cierra este hallazgo y el `.git` del tema, ya expuesto.

**6. Purgar la PII de los scripts de siembra (P7, Media).** `cli/seed_rap.php` lleva una cédula y una
ficha reales. Sustituir por datos sintéticos, y purgar la historia si el repo es compartido. En una
entidad pública sujeta a Habeas Data (Ley 1581/2012) es cumplimiento, no higiene opcional.

**7. Declarar las dependencias y recuperar la CI (P4, P8, Media).** Restaurar `thirdpartylibs.xml`
con la versión de FontAwesome (lo tenía `migration`), añadir SRI o quitar el fallback a CDN, y
recuperar `.github/workflows/moodle-release.yml` conectando `phpunit`. Las dos cosas existían en la
versión anterior del proyecto y se perdieron al reescribir.
