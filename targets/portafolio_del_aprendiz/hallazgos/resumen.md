**Portafolio del Aprendiz es un plugin de Moodle bien construido en su control de acceso, que se
despliega con éxito en este ambiente, pero cuyo manual describe el sitio equivocado y cuya pieza
más específica —los resultados de aprendizaje— depende de una base de datos que el repositorio no
entrega.** La lista de prioridades decía «DEPLOY.md NO ENTREGADO»: era cierto el 19/08, y dejó de
serlo el 25/08 a las 12:11, cuando el equipo subió un `DEPLOY.md` de 658 líneas a `feature/v2`
—durante esta misma auditoría—. El reclamo hoy no es sobre la entrega (llegó, y está bien escrito),
sino sobre su contenido.

El proyecto son en realidad tres plugins distintos en dos repositorios; se auditó el vivo y más
reciente, **`local_portafolio` en `feature/v2 @ 9674bda`** (rama en desarrollo activo: 10 commits el
día de la auditoría). El predecesor `block_portaapre` —lo que documentan los dos manuales viejos que
circulan en el workspace (un `.docx` y un `DEPLOYMENT_STAGING.md`)— ya no se despliega: devuelve 404
en producción. Ese desajuste, docs que describen un plugin que el equipo abandonó, es parte del
hallazgo.

Se desplegó `local_portafolio` sobre el core Zajuna de esta máquina siguiendo el manual, y funcionó:
el plugin se instala, las páginas renderizan, el smoke test pasa, y convive sin tocar a los otros
cuatro proyectos del core compartido. Pero el manual documenta el «entorno de referencia» del
desarrollador —Apache, HTTP, PostgreSQL en 5433— y el ambiente real es nginx, HTTPS y 5432, hasta el
punto de que el propio smoke test del manual (§16.1, «debe responder `Server: Apache`») falla aquí,
donde el servidor es nginx (**P6, Media**). No impide desplegar, pero desorienta a quien lo haga.

Dos hallazgos son **Altos**. **P1:** al instalar, el plugin escribió en la base de datos del core la
credencial por defecto de su conexión a la réplica externa —usuario `postgres` (superusuario),
contraseña `12345`—; un despliegue que no pase a mano por la UI queda con eso como credencial activa.
**P3:** la pantalla de Resultados de Aprendizaje (RAP), que es la mitad del valor del plugin, depende
de una base de datos externa (`integracion`) que el repositorio no define y que el propio manual
reconoce no poder documentar. Sin ella, la pantalla queda vacía —y en silencio, porque el código se
traga el error (**P2**)—. Ambos se rodearon en el laboratorio (un rol de solo lectura para P1, el
esquema reconstruido leyendo el código para P3), lo que permitió MEDIR que el plugin funciona
end-to-end; pero la reconstrucción es del laboratorio, así que esa pantalla se declara NO
AUTORITATIVA. Se contrastó contra el servidor del equipo, donde la BD real existe y la pantalla
muestra 83 resultados reales.

Lo que **sí resistió, con autoridad**, es el control de acceso —el corazón de un portafolio, que
mezcla datos de aprendices distintos—. Con las cuentas REALES entregadas, por navegador y en el
servidor del equipo, se recorrió la matriz completa: el aprendiz solo alcanza su propio portafolio;
manipular `?userid=` de un compañero lo frena («no tienes permiso»); el instructor gestiona a los
aprendices de SU curso pero no a otros; y el guardián de matrícula frena incluso al instructor
cuando el aprendiz no está en el curso. Seis ejes, todos coherentes, con capturas. Es una matriz
AUTORITATIVA —el caso positivo que en auditorías anteriores quedó pendiente por cuentas caducadas—.

El resto son hallazgos de higiene: un `.git` que el manual deja servible al mandar clonar en el
webroot (**P5**), datos personales reales (una cédula) versionados en un script de siembra (**P7**,
que en Colombia toca la Ley de Habeas Data), ceguera de dependencias porque no hay manifiesto y
FontAwesome va empotrado sin versión (**P4**), y una CI que el proyecto tenía en su versión anterior
y perdió al reescribir (**P8**). Ninguno es una vulnerabilidad de aplicación explotable sin sesión:
la superficie pública del plugin son redirecciones a login y ficheros estáticos, y ZAP no encontró
nada propio del plugin —sus 68 alertas (67 tras deduplicar por regla) son del core de Moodle (versión de nginx, cabeceras,
MathJax por CDN), compartidos por todos los plugins—. La calidad de código son 205 avisos de estilo
de Sonar (paréntesis redundantes, complejidad, strings duplicados), cero con severidad de seguridad.

**Veredicto: GATE FAILED**, por los umbrales de despliegue (cero tolerados, hay hallazgos) y de
DAST (67 > 40, casi todo ruido del core). Pero el mensaje real es más matizado que el semáforo: el
plugin es sólido donde más importa (autorización), se despliega bien, y sus dos riesgos altos son de
configuración de despliegue y de reproducibilidad —no de código vulnerable—. Es un buen plugin con
un manual que describe la máquina equivocada y una dependencia que falta entregar.
