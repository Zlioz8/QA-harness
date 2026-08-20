### 2.a ✅ El enrutamiento por `.htaccess` protege lo que debe — Responsable: DevOps/Infra

Comprobado en los dos entornos, con resultados idénticos: `/adi/.env`, `/adi/app/App.php`,
`/adi/composer.json`, `/adi/vendor/autoload.php`, `/adi/dashboard/config/define.php` y las
migraciones responden **403**. El `AllowOverride All` está activo y las reglas se aplican. El
fallo de §3.1 es una limitación del patrón usado, no una configuración ausente.

### 2.b ✅ El control de acceso por rol funciona como está escrito — Responsable: Backend

Con dos cuentas de privilegio distinto contra el despliegue local, `RoleMiddleware` deniega con
**403** en seis de los siete endpoints de escritura reservados a `super`. La política declarada en
el código se aplica de verdad. (El séptimo, `/adi/users/store`, responde 302 porque
`CsrfMiddleware` rechaza antes — no es un fallo de autorización.)

### 2.c ✅ La sesión se endurece antes de iniciarse — Responsable: Backend

`index.php` fija los parámetros de cookie **antes** de `session_start()`: `httponly`, `samesite=Lax`
y `secure` condicionado a HTTPS. Y el identificador de sesión se regenera al autenticar, lo que
cierra la fijación de sesión. Es correcto y merece decirse.

### 2.d ✅ Sin secretos verificados vivos — Responsable: Backend

TruffleHog recorrió la historia completa comprobando contra las APIs de los proveedores: **0
credenciales verificadas como activas**. Los secretos de §3.2 y §3.5 son reales y hay que
rotarlos, pero no son de proveedores que TruffleHog pueda validar en línea.

### 2.e ✅ Sin inyección SQL detectada — Responsable: Backend

semgrep con `p/security-audit`, `p/secrets` y `p/owasp-top-ten` sobre 342 archivos PHP: tres
avisos de `tainted-sql-string`, ninguno confirmado como inyección explotable tras revisión. El
acceso a datos usa PDO con parámetros.
