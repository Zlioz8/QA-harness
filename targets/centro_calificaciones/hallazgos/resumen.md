El Centro de Calificaciones son tres repositorios de la fábrica —`centro_de_actividades`
(`lmsActividad`), `centro_de_resultados` (`lms-califica`) y `centro_de_calificaciones_sincronizacion`
(`calificaciones`)— más un plugin de Zajuna y un sincronizador PostgreSQL→MongoDB con systemd. Todo
el código es de Victor Manuel Echeverri. Es el proyecto más complejo auditado hasta ahora, y el
veredicto es **GATE FAILED**, con un hallazgo **Crítico probado en vivo** que domina todo lo demás.

**Lo urgente (P1, Crítico):** el punto de entrada del Centro de Actividades,
`config/login_config.php`, inicia sesión a partir de la identidad que recibe por la URL
(`user`, `courseid`, `roleid`) y **no valida el `sesskey`** —de hecho no exige ninguna sesión de
Moodle—. Se probó contra el despliegue REAL del equipo (`zajunavideo5.com`, autorizado): con un
`sesskey` deliberadamente inválido y sin sesión previa, el sistema abrió sesión como otro usuario
(un instructor) y renderizó su Centro de Calificaciones. Como los identificadores de usuario y curso
son enteros secuenciales, cualquiera con acceso a la red puede suplantar a otro. Es un bypass de
autenticación con suplantación de identidad (IDOR) y debe cerrarse antes que nada.

**Lo grave de fondo (P2, P3, P4):** hay credenciales de superusuario de PostgreSQL en claro —en la
historia git (recuperables) y en un `.sql` vigente— y un token de SonarQube filtrado; hay que
rotarlos ya. Y la arquitectura mete la lógica del módulo (45 funciones, `postgres_fdw`, cinco
esquemas foráneos) **dentro de la base de datos del core Moodle que comparten cinco proyectos**, lo
que hace el despliegue invasivo y no reversible con limpieza.

**El manual describe otra máquina (P5, P7):** manda Apache donde el destino real usa nginx, exige
PHP 8.2 donde corre 8.1, y trae parches al core que ni compilan. Y seguir el manual (Apache sin
bloqueo de ficheros ocultos) sirve el `.env` y el `.git` por HTTP —una fuga de credenciales que se
encadena con la historia git—; el servidor real se salva solo porque usa nginx.

**Estado del despliegue:** se levantó un despliegue integrado y seguro en esta máquina (contenedor
Apache+PHP 8.2, MongoDB 7, BDs sandbox propias, conviviendo con los 18 contenedores de los otros
proyectos sin tocarlos). Las apps arrancan y sirven su superficie, pero las pantallas con datos
dependen de las modificaciones invasivas al core que un audit seguro no aplica al core vivo; por eso
el control de acceso se validó autoritativamente contra el servidor del equipo. Hay reparaciones
concretas y ordenadas por impacto en la sección de recomendaciones: la primera, cerrar P1.
