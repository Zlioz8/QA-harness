# Guion de flujos de navegador (MCP) — reportes_de_cursos (ZAJUNA Early Alert)

Flujos REALES del usuario a recorrer con el servidor MCP del navegador, primero en LOCAL
(el despliegue por DEPLOY.md sobre el core de esta máquina, `http://nginx.zajuna.com/zajuna`) y
después en el SERVIDOR de pruebas (`https://zajunavideo5.com`, que ya sirve `/zea-api` y
`/zea-dashboard`). Cada flujo declara qué hallazgo del informe contrasta y qué evidencia deja.

Credenciales reales entregadas por el operador (a `target.env.local`, no aquí): 4 cuentas de
instructor, una por ficha/curso, y 1 aprendiz (`1089379340 / Daniel_07340@`). El aprendiz es el
rol de bajo privilegio de la matriz.

- **F1 · Entrada al tablero embebido.** En Moodle, curso con el bloque ZAJUNA Early Alert →
  abrir el tablero (`/zea-dashboard/?courseid=<ID>`). Observar en la pestaña de red la cadena
  `login.php`/`token.php` → `Authorization: Bearer` a `/zea-api/api/v1/reports/...`. Confirma que
  el SSO de dos saltos funciona por el mismo origen (contrasta el modelo de auth del informe).

- **F2 · Consulta «mi estado en Zajuna» como aprendiz.** Con la cuenta de aprendiz, seguir el
  flujo «consulta mi estado» que el operador indicó. Observar si el aprendiz alcanza algún reporte
  del tablero: `token.php` debería darle 403 (sin `viewreports`; db/access.php solo lo concede a
  teacher/editingteacher/manager). Un tablero con datos aquí es un hallazgo de autorización.

- **F3 · Manual del Aprendiz.** Recorrer el flujo «Manual del Aprendiz» indicado por el operador
  y registrar qué expone: si desde ahí se llega a datos de otros aprendices o a rutas del tablero.

- **F4 · /metrics público.** Pedir `/zea-api/metrics` sin sesión desde el navegador → 200 con
  texto Prometheus (contrasta el hallazgo de exposición; DEPLOY.md §17 lo da por protegido).

- **F5 · Contrato roto /api-zea.** Pedir `/api-zea/health` → observar 200 con el HTML del CMS en
  vez del JSON del servicio (contrasta la incongruencia de la URL de producción del OpenAPI).

- **F6 · Cross-course (IDOR por curso).** Con un instructor de la ficha X ya en el tablero,
  cambiar en la petición `courseid` al de la ficha Y (donde NO es instructor) → `AuthorizeCourse`
  (jwt.go:70) debe devolver 403 forbidden. Un 200 sería fuga entre cursos (contrasta la matriz).

- **F7 · Vista previa / reporte pesado.** Abrir el reporte más costoso (activity-matrix o
  rap-detail) para una ficha con muchos aprendices → observar si responde, tarda o devuelve un
  error crudo. En #3 la vista previa reveló un 502 que ninguna herramienta automática vio; aquí se
  mira lo mismo contra datos reales.

- **F8 · Reinicio de sesión / expiración del JWT.** Dejar el tablero abierto > 600 s (vida del
  JWT de curso, token.php) y forzar una petición → observar si el SPA renueva el token
  (login.php → token.php) o si el usuario cae a un estado roto sin aviso.

Evidencia por flujo (URL, resultado, logs de consola y red, capturas) → `reports/reportes_de_cursos/mcp/journeys.md`.
Los logs de red/consola crudos, con `tools/mcp-traza.sh reportes_de_cursos`, a
`reports/reportes_de_cursos/mcp-evidencia/`.
