**Encuestas es un proyecto maduro con un agujero puntual y grave en su despliegue, y una
superficie pública que resistió todo lo que se le probó.** La lista de prioridades decía «DEPLOY.md
NO ENTREGADO»: es cierto al pie de la letra —no existe ningún fichero con ese nombre— pero falso
en lo que importa. La documentación de despliegue existe, son 137 líneas bien escritas
(`deploy/README-DESPLIEGUE.md`) acompañadas de todos los artefactos que describe. El reclamo
correcto es «renómbralo a la convención», no «no lo entregaste».

Se desplegó el backend en esta máquina siguiendo ese manual al pie de la letra, y ahí apareció el
hallazgo central de la ronda (**D1, Alta**): **un despliegue desde cero NO arranca**. El
`10-search-path.sql` fija el `search_path` al schema `Produc` pero nunca lo crea, y las migraciones
mueren con «Invalid schema name». Es un arreglo de una línea (`CREATE SCHEMA IF NOT EXISTS
"Produc"`), pero hasta aplicarlo el manual está incompleto justo en su punto más crítico: el
arranque. Tras el fix, las migraciones completaron y la API respondió correctamente. Alrededor de
PgBouncer hay dos fricciones más (D2, D3): una dependencia circular no documentada para generar el
`userlist.txt`, y que ese fichero de credenciales no está protegido por el `.gitignore`.

En seguridad, la superficie pública se comportó bien: sin sesión, todo lo autenticado responde 401;
el path-traversal en el servido de ficheros se rechaza (400/404); la descarga firmada exige firma
(403); el limitador de login está activo (5/min); y el fallback de la SPA a producción hasta cierra
un redirect abierto. El único hallazgo de seguridad real del despliegue del equipo es de
infraestructura, no de código: **el origen Apache está publicado en claro en el puerto 8000**
(la API entera sin TLS, ALTA). Los secretos en la historia de git (una contraseña de BD en un
markdown, una `APP_KEY` en un respaldo `.env`) son de higiene y hay que rotarlos.

La **matriz de autorización se ejecutó** sobre el despliegue local, recorrida por navegador (MCP)
con sesión autenticada: 9 casos en tres ejes distintos (cerco del aprendiz, gate de creación de
encuestas, gate de administración) — **TODA COHERENTE**. El aprendiz solo alcanza sus 3 rutas y
recibe 403 en todo lo demás; el funcionario gestiona encuestas pero no administra usuarios; nadie
escala. La autorización de este proyecto es sólida. Con una salvedad de método: se midió con
cuentas de la aplicación creadas por el laboratorio, así que es **NO AUTORITATIVA** — mide el
control de acceso sobre los roles que elegimos, no sobre los que la fábrica asigna. La versión
autoritativa exige las cuentas reales por SSO: las tres entregadas SÍ se verificaron (válidas, y sus
roles reales no coinciden con sus rótulos — una misma persona es instructora en unos cursos y
aprendiz en otros), pero el login web de Moodle rebota a caplms y hay que reparar ese rebote para
completar el SSO.
