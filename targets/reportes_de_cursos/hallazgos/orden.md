Agrupado por a quién le toca, en orden de lo que primero desbloquea a los demás.

**Luis Andrés Ríos (desarrollador) — despliegue, lo que impide un arranque limpio:**
1. **C1 (Alta):** que `recreate-analytics-mv.sh --force` aplique también `login.sql`, o que el
   DEPLOY.md §8/§15 mande ejecutarlo explícitamente. Sin esto la API no arranca desde cero.
2. **C4 (Alta):** cerrar `/zea-api/metrics` al público (autenticación, o restringir la `location`
   del proxy a una red interna). Hoy sirve reconocimiento operativo a internet.
3. **C5 (Media):** alinear la URL de producción del contrato OpenAPI (`/api-zea`) con la que el
   despliegue sirve (`/zea-api`), o al revés.
4. **C2, C3 (Media):** documentar en el DEPLOY.md el caso «Moodle bajo subpath»: que
   `install-nginx.sh` no aplica y que `VITE_MOODLE_BASE` es entonces obligatoria y de build-time.
5. **`.env.production` versionado** y **11 secretos en la historia git**: sacar el fichero del
   control de versiones y rotar/purgar lo que la historia arrastra (verificar en triaje cuáles son
   marcadores de `.env.example` y cuáles reales — la clave privada RSA del backend predecesor
   `jwt_private.pem` merece confirmación de que no es la de firma actual).
6. **Cabeceras de seguridad ausentes + versión del servidor expuesta** (Playwright e2e y ZAP): el
   tablero no envía CSP/X-Frame-Options/HSTS/X-Content-Type-Options, y el `Server` de nginx anuncia
   versión. Añadir cabeceras en la `location` del proxy y `server_tokens off`.
7. **Imágenes del SPA sobre presupuesto** (Playwright main-thread-budget, 3 comprobaciones): el
   bundle sirve imágenes demasiado pesadas (p. ej. `fondologin.webp`). Optimizar/redimensionar.
8. **C10 (Baja, defensa en profundidad):** que el middleware de la API valide el claim `typ` del
   JWT (aceptar solo `typ:"course"` en `/api/v1/reports/*`). Hoy la separación entre token de
   identidad y de curso la sostiene solo la ausencia de `courseid` en el de identidad.
9. **C9 (Media, operativo):** el login del tablero en el servidor rebota a `caplms.sena.edu.co`
   (bug de enrutamiento del host ya conocido). Revisar para que el flujo de autenticación del
   tablero sea usable donde se sirve el tablero.
10. **UX (menor):** el modal del aprendiz conflaciona «sin permiso» con «sesión expirada»; usar el
    texto que ya devuelve `token.php` («no tienes permiso para ver los reportes de esta ficha»).

**Líder técnico — calidad, sin bloquear el despliegue:**
11. **578 hallazgos de calidad (Sonar)**: la mayoría son complejidad cognitiva (`php:S3776`) en las
    clases `external/*` del plugin. Deuda técnica, no seguridad; priorizar en un ciclo aparte.

**Equipo (entrega para R2):**
12. **Cuentas de instructor vigentes.** Las 5 entregadas están CADUCADAS (rechazadas en el
    servidor). Con una válida se cierra el único ⟨PENDIENTE⟩: el caso positivo «instructor SÍ ve»
    con cuenta REAL sobre el servidor (la denegación del aprendiz ya está validada autoritativa;
    la concesión se demostró en local con cuentas de prueba).
