1. **DevOps/Infra — hoy.** Rotar la credencial de `superadmin` (§3.3) y el token de SonarQube
   (§3.2). Están publicados; todo lo demás puede esperar a que esto no.
2. **DevOps/Infra — hoy.** Cerrar el acceso a `.git` (§3.1). Mientras siga abierto, cualquier
   rotación es provisional: la historia sigue siendo descargable.
3. **Backend — esta semana.** Retirar las credenciales por defecto de `define.php` (§3.5) y rotar
   la contraseña de Oracle `lmsmoodle`. Va después de los dos anteriores solo porque requiere
   tocar código.
4. **Backend — esta semana.** Commitear `composer.json` y `composer.lock` (§3.4). Es de esfuerzo
   bajo y desbloquea la dimensión de CVE de dependencias, que hoy no mide nada.
5. **Backend — esta semana.** Corregir el orden de la migración `006` y el esquema de la `004`
   (§3.6), y commitear la definición de `synchronized_events` (§3.7). Los tres juntos: son el
   mismo problema visto por tres sitios.
6. **Backend — corto plazo.** Registrar `CsrfMiddleware` en los seis controladores que no lo
   llevan (§3.9), empezando por `/adi/scripts/store`, que es el de mayor impacto.
7. **DevOps/Infra — corto plazo.** Cabeceras de seguridad y `Options -Indexes` (§3.11, §3.10).
   Son configuración de Apache, no tocan la aplicación.
8. **Backend — corto plazo.** Registrar la excepción original antes de sustituirla (§3.12).
   Hacerlo antes que §3.8 abarata su diagnóstico.
9. **Líder Técnico — a planificar.** Integración continua mínima (§3.13). Es lo que evita que
   esta lista se vuelva a llenar.

**Para la próxima ronda:** entregar una **segunda cuenta de menor privilegio** (rol `support`) en
el entorno de validación. Sin ella la matriz de autorización no puede medirse contra el
despliegue real, y esa dimensión queda NO DISPONIBLE.
