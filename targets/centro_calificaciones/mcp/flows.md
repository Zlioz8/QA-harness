# Guion de flujos por navegador (MCP) — Centro de Calificaciones

El plan de lo que el recorrido de navegador DEBE ejercitar en este proyecto. La ejecución y las
capturas están en `reports/centro_calificaciones/mcp/journeys.md` y `reports/.../mcp-evidencia/`.

## Por qué ESTE proyecto necesita el recorrido de navegador

El eje de la auditoría es el control de acceso del SSO (`config/login_config.php`): la app inicia
sesión a partir de la identidad que recibe por la URL. Ninguna herramienta estática o de superficie
(gitleaks, semgrep, ZAP sin sesión) puede DEMOSTRAR que un usuario alcanza la sesión de OTRO — eso
solo se ve invocando el endpoint y observando qué sesión se establece. Por eso el hallazgo P1 se
prueba recorriéndolo con el navegador.

## Flujos a recorrer

1. **Bypass del SSO con sesskey inválido (P1, el eje).** Sin sesión de Moodle previa, invocar
   `GET /lmsActividad/config/login_config.php?user=<víctima>&courseid=<curso de la víctima>&roleid=<rol>&sesskey=BASURA_INVALIDA`.
   Comprobar si establece sesión (302 → `views/principal.php`) y si `principal.php` renderiza 200
   AUTENTICADO como la víctima. Si lo hace, el sesskey no se valida y no se exige sesión → bypass.
   Capturar `principal.php` con la identidad de la víctima. **Alcance ético: solo demostrar el
   establecimiento de sesión; no navegar los datos académicos de la víctima ni modificar nada.**
2. **Control: tripleta que NO existe.** Invocar con `(user,courseid,roleid)` sin matrícula. Debe
   redirigir a `/zajuna/` (obtenerSession no devuelve fila) — confirma que el único «control» es la
   existencia de la matrícula, no la validación del sesskey.
3. **Superficie de fichero oculto (P5).** `GET /lmsActividad/.env` y `/.git/config` — comprobar si el
   servidor los sirve (200 = fuga) o los bloquea (403). Hacer en LOCAL (Apache del manual) y contra
   el servidor real (nginx), para separar el defecto del manual del comportamiento del destino.

## Dónde ejecutarlo, y con qué autoridad

- **AUTORITATIVA** en `https://zajunavideo5.com` (despliegue real y funcional del equipo), con las
  cuentas REALES entregadas por el operador QA (`admin_slider`, `comunidades1`), verificadas contra el
  servidor (`token.php`) antes de usarlas. La tripleta víctima se obtiene por web service de admin
  (`core_enrol_get_enrolled_users`), en lectura. Solo navegación; ninguna dimensión automatizada
  (ZAP/k6) contra este servidor: no es nuestro. `zajunavideo5.com` se añade a `/etc/hosts` mientras
  dura el recorrido (el navegador MCP no resuelve DNS público) y se revierte al terminar.
- **NO AUTORITATIVA** en el despliegue local (`http://127.0.0.1:8097`): sirve la superficie estática y
  la verificación de `.env`/`.git` (P5), pero NO los flujos con datos — el despliegue local no es
  funcional sin las 45 funciones que el manual mete en el core (P4).

## Qué NO se recorre, y por qué

La matriz de autorización completa entre roles (instructor vs aprendiz, cruce de cursos) sobre datos
reales NO se recorre en profundidad: hacerlo exigiría navegar registros académicos de personas
reales, más allá de lo necesario para probar el bypass. Con P1 demostrado —cualquiera entra como
cualquiera— la matriz de roles pierde sentido hasta que se cierre P1: el control de acceso está roto
en la puerta, no en las pantallas internas.
