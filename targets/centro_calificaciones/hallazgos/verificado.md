Lo que se comprobó y salió BIEN, o quedó acotado con evidencia:

- **El repositorio auténtico existe y se identificó** (Victor Manuel Echeverri). Tres repos en la
  fábrica, ramas de auditoría elegidas por recencia y ancladas a SHA (3f84cfa / d084378 / fd04cc9).
  El reclamo de «clona de GitHub personal» está **resuelto** en la entrega vigente del repo (22/08):
  clona de `git.fsrisaralda.com`. Solo los `.md` viejos del workspace siguen apuntando a GitHub.
- **Los manuales SÍ están entregados** (en `docs/` del repo). La lista de prioridad los daba por no
  entregados: era falso.
- **Convivencia intacta:** el despliegue de esta auditoría (contenedor Apache+PHP 8.2 en `:8097`,
  MongoDB 7 en `:27117`, BDs sandbox propias) convive con los 18 contenedores de los otros proyectos
  sin tocarlos. Verificado antes y después: los 18 siguen vivos y `/encuestados/`, `/zea-dashboard/`,
  `/zea-api/health`, `:8089` responden igual. No se modificó el core (nginx, BD `moodle`, BD
  `integracion` de #7): todo reversible, baselines en `baselines/core-centro-calificaciones-precambios/`.
- **Las dependencias no traen CVEs graves:** Trivy fs → 1 solo hallazgo, severidad LOW
  (`symfony/polyfill-intl-idn`). El problema de dependencias es de proceso (lockfiles, SwiftMailer
  abandonado — P8), no de un CVE crítico abierto.
- **Sin secretos verificados VIVOS:** trufflehog no confirmó ninguna credencial respondiendo a un
  proveedor externo (son credenciales internas de BD; su riesgo es la recuperabilidad, P2, no una
  clave SaaS activa).
- **El bypass P1 se probó de forma acotada y ética:** solo se demostró el establecimiento de sesión
  contra el servidor real; no se extrajeron datos de la víctima ni se modificó nada. Evidencia
  redactada en `mcp-evidencia/`.

Responsable de las correcciones de código: **Victor Manuel Echeverri**. Responsable de la
verificación y del despliegue de auditoría: QA (laboratorio).
