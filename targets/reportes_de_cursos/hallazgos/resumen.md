**El proyecto se desplegó con éxito desde su propio repositorio y su API queda correctamente
cerrada tras autenticación — pero el manual de despliegue no concuerda con lo que el sistema
exige para arrancar, y hay una exposición de datos operativos abierta a internet.** Es la primera
ronda: ningún hallazgo arrastra historial todavía.

Lo primero y más importante para el equipo: **el DEPLOY.md, seguido al pie, deja la API sin
arrancar.** El servicio Go se niega a servir hasta que existan sus 6 vistas materializadas
(comprobación deliberada, para no servir reportes vacíos), pero el único script que el manual
manda ejecutar, `recreate-analytics-mv.sh --force`, solo crea 4 de las 6: no aplica nunca
`login.sql`, donde viven las otras dos. Lo medimos desplegando de verdad sobre el core de esta
máquina: la API entró en bucle de reinicio con «faltan 6 relaciones… mv_zea_login_daily,
mv_zea_login_resources» hasta que aplicamos `login.sql` a mano (§C1 del cotejo). Cualquiera que
despliegue desde cero tropieza con esto.

Lo segundo es de seguridad: **`/zea-api/metrics` es público en internet** (200, sin token, en
`https://zajunavideo5.com`). El manual (§17) lo da por seguro «porque el servicio escucha en
loopback», pero detrás del proxy sale, y expone el inventario de rutas, los internos del pool de
conexiones a la base, los conteos de peticiones por ruta y hasta un contador de errores 500. No
filtra credenciales, pero es un mapa de reconocimiento servido a cualquiera (§C4).

El resto son incongruencias entre el manual y la integración real en un Moodle que vive bajo un
subpath (`/zajuna`), no en la raíz que el manual asume: `install-nginx.sh` reescribiría el site y
tumbaría lo que ya corre, y `VITE_MOODLE_BASE` —que el manual degrada a «no obligatoria»— es de
hecho obligatoria y de tiempo de compilación aquí (§C2, §C3). Y el contrato OpenAPI declara una
URL de producción, `/api-zea`, que el despliegue no sirve: pedirla devuelve la web del CMS con un
200 engañoso (§C5). Todo esto está en `COTEJO_DESPLIEGUE.md`, que es el corazón de esta ronda.

**El control de acceso está validado y funciona, con una cuenta REAL y contra el servidor del
equipo.** Se inició sesión en `zajunavideo5.com` con el aprendiz real entregado (cédula
1089379340) y se pidió el token de reportes para sus tres cursos matriculados (9866, 9401,
23644): los tres devuelven «no tiene los permisos… Ver reportes de riesgo de todos los aprendices
matriculados» — es la comprobación de capacidad `viewreports` contra la BD real, no contra el
archetype supuesto. Y la API, con la cookie de sesión del aprendiz pero sin token de curso,
responde 401. Un aprendiz no alcanza los reportes por ninguna vía: **denegación autoritativa,
verificada, correcta.** El mecanismo de aislamiento entre cursos también se validó (token de un
curso pidiendo otro → **403 «forbidden: course mismatch»**). Dos matices: la API **no comprueba el
`typ` del JWT** —defensa en profundidad, no explotable hoy porque el token de identidad real no
lleva `courseid` (C10)—, y el login del tablero en el servidor QA rebota a `caplms.sena.edu.co`
(bug de enrutamiento ya conocido, C9).

El lado «permitido» de la matriz se cerró **en el despliegue local**, no en el servidor: las **5**
cuentas de instructor entregadas están **caducadas** —las cinco rechazadas en `zajunavideo5.com`
con «datos de acceso incorrectos», y también por el web service—, así que no sirven para el caso
positivo contra el servidor. En su lugar, con dos cuentas de prueba locales sobre el mismo curso
(instructor con `viewreports`, aprendiz sin ella) se demostró la matriz completa: **instructor →
token.php 200 y reporte 200; aprendiz → token.php 403 «No tienes permiso para ver los reportes de
esta ficha».** Es no-autoritativo para «quién debe tener acceso» (las crea el laboratorio), pero
demuestra el MECANISMO de punta a punta; el «quién» ya se validó con el aprendiz real arriba. Lo
único que queda ⟨PENDIENTE⟩ es el caso positivo con una cuenta de instructor REAL vigente.

**Lo que salió bien y conviene decir claro:** el proyecto SÍ entregó su DEPLOY.md en `dev` (818
líneas, de las mejores que ha visto esta auditoría; el seguimiento de la fábrica lo daba por no
entregado por una foto vieja, ya corregido); el despliegue local funcionó de punta a punta
—plugin, upgrade, 6 MV, contenedores sanos, nginx, `/zea-api/health` → 200—; la API cierra bien
(todo `/api/v1/reports/*` responde 401 sin JWT, y una ruta inventada da 404 honesto, no el 200
del catch-all que sí afea a otros proyectos); y el servidor corre en su postura más cerrada, con
el login autónomo deshabilitado (§C6). Recorrido el tablero con navegador como instructor, todas
las pantallas de reportes cargan (200, sin errores de consola) y los reportes sin datos muestran un
estado vacío correcto — **ningún 502**, a diferencia de la vista previa de #3.

**Lo único que esta ronda NO pudo medir, y no debe leerse como «sin hallazgos»:** el lado
«permitido» de la matriz de autorización CONTRA EL SERVIDOR (instructor SÍ ve sus reportes en
`zajunavideo5.com`), porque las 5 cuentas de instructor entregadas están caducadas. Ese caso
positivo se demostró en el despliegue local (arriba); contra el servidor queda ⟨PENDIENTE⟩ de
credenciales vigentes. La denegación de bajo privilegio, que es lo que de verdad protege, sí quedó
AUTORITATIVA con el aprendiz real.

Los 623 hallazgos de análisis estático quedan **sin triar**: la mayoría de los marcados «críticos»
son complejidad cognitiva de Sonar (`php:S3776`), que es deuda de calidad, no seguridad — cuentan
para la deuda, no para el riesgo, y separarlos es el trabajo de triaje de la próxima ronda.

**Cobertura del laboratorio en esta ronda:** se ejecutaron TODAS las dimensiones aplicables —
secretos, dependencias, SAST, calidad (Sonar), SBOM, contrato de despliegue, contrato de API
(Spectral), DAST (ZAP, 23 alertas, ninguna alta), **carga (k6): 0 % de error y p95 = 5,5 ms**,
y la **matriz de autorización (Playwright): 6/6**. `api-fuzz` (Schemathesis) se ejecutó pero es
**NO CONCLUYENTE** (el comando del laboratorio no salta el TLS autofirmado ni inyecta el JWT, y la
API está 100 % autenticada; el contrato lo cubre Spectral — ver bitácora L-R4-05). Qodana es NO
DISPONIBLE (imagen de pago sin token). Declaradas NO APLICA: MobSF, JMeter, dispositivo,
imagen-Docker. Ninguna dimensión quedó en silencio.
