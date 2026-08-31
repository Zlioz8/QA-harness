Lo que se comprobó y salió **bien** — se registra para que conste que se miró, no solo lo que falló:

- **El control de acceso es sólido y está bien centralizado.** De los 16 puntos de entrada HTTP,
  las 12 que pueden mostrar el portafolio de un usuario (`view.php` y las 11 de tipo actividad)
  delegan en un único resolvedor (`local_portafolio_resolve_target_user`, `lib.php`) que exige DOS
  cosas antes de mostrar el de OTRO: la capability `local/portafolio:viewother` Y que el usuario
  esté matriculado (`is_enrolled`). `participantes.php` usa `require_capability` directo; `index`/
  `cursos` son de contexto de sistema; y las 16 llaman a `require_login` como primera instrucción.
  No hay una sola página que se salte el control. *(Johan Sebastián Valle)*
- **La matriz de autorización es AUTORITATIVA y coherente.** Con las cuentas REALES por navegador en
  el servidor del equipo, los 6 ejes dieron lo esperado: aprendiz solo ve lo suyo; `?userid=` ajeno
  → denegado; `participantes.php` sin capability → denegado; instructor gestiona a los suyos;
  instructor ve el portafolio de su aprendiz; guardián de matrícula frena al instructor fuera de su
  curso. Con capturas en `mcp-evidencia/`. *(Johan Sebastián Valle)*
- **El plugin se despliega con éxito y convive sin interferir.** Se instaló en el core compartido
  por otros 4 proyectos sin tocar puertos, contenedores ni el vhost; los 18 contenedores vecinos y
  sus endpoints siguieron respondiendo igual antes y después. *(Johan Sebastián Valle)*
- **El smoke test del propio manual pasa** (5 de 6 pasos limpios; el 6º —`Server: Apache`— es un
  desajuste del manual, no del plugin, ver P6). *(Johan Sebastián Valle)*
- **La degradación sin la BD externa es la que el manual promete:** `resultados.php` sin
  `integracion` devuelve 200 «sin resultados», no un 500. (Que lo haga en SILENCIO es P2, un matiz
  de criterio, pero no rompe.) *(Johan Sebastián Valle)*
- **El plugin renderiza end-to-end contra la BD externa**, verificado en los dos entornos: 83 RAP
  reales en el servidor del equipo, y los RAP reconstruidos en el despliegue local con estado
  Aprobado/Desaprobado/Pendiente. La lógica de resolución de modalidad, tabla por semestre y match
  por documento funciona. *(Johan Sebastián Valle)*
- **Corre en PHP 8.1**, pese a que el manual pide 8.2: los 46 ficheros pasan `php -l` con 8.1.34 y
  las 11 páginas responden 200. Buena compatibilidad. *(Johan Sebastián Valle)*
- **Rendimiento holgado bajo carga de lectura autenticada:** k6 con 5 VUs durante 60s dio 0% error
  y p95 76 ms sobre las 11 páginas, 800 peticiones. (Sobre datos vacíos en local; la página con la
  BD real sería más cara, pero la base de render es rápida.) *(Johan Sebastián Valle)*
- **Sin vulnerabilidades de aplicación explotables sin sesión.** La superficie pública son
  redirecciones 303 a login (todas las páginas protegidas) y estáticos. Los 68 hallazgos de ZAP son
  del core de Moodle (versión de nginx, CSP, cookies, MathJax por CDN), no del plugin. *(Johan Sebastián Valle)*
- **La calidad de código es de estilo, no de seguridad:** los 205 avisos de Sonar son code smells
  (paréntesis redundantes S6600, complejidad S3776, strings duplicados S1192); CERO con
  severidad de seguridad. *(Johan Sebastián Valle)*
