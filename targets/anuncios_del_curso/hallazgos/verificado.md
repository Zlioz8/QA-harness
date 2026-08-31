Lo que se comprobó y **salió bien** en esta ronda (responsable del artefacto: QA):

- **Matriz de autorización — sin bypass (14/14).** `editingteacher` gestiona; `student` recibe
  `nopermission` en `manage.php`, `adding_image.php`, `edit.php`, `delete.php`; `student` de otro
  curso es redirigido (no matriculado); el anónimo no alcanza nada. Verificado con curl + navegador +
  Playwright. Es NO AUTORITATIVA (cuentas del laboratorio), pero el MECANISMO queda demostrado.
- **Visibilidad por imagen — respetada.** Una imagen puesta a `visible=0` no aparece en `view.php`,
  ni en el carrusel embebido del curso, ni en `carousel_content.php`, ni siquiera en el HTML fuente,
  vista como student. La familia de fallo "imagen oculta servida igualmente" se buscó y no está.
- **`carousel_content.php` exige `sesskey`** antes de servir contenido: el endpoint AJAX está
  protegido de CSRF (a diferencia de `manage.php`, I1).
- **Disponibilidad temporal** (`availablefrom`/`availableuntil`): oculta el carrusel fuera de la
  ventana y lo restaura dentro. Funciona.
- **Despliegue e instalación verificados en la base**, no por pantalla: 26→27 módulos, dos tablas
  creadas sin colisión, toggle sembrado, 13 concesiones de capability, entradas en `upgrade_log`.
- **Convivencia preservada:** tras instalar, los cuatro despliegues vecinos siguen vivos y el core
  sigue sirviendo `/`, `/zajuna`, `/encuestados`, `/api`, `/zea-*`. No se tocó nginx, pg_hba, roles
  ni puertos.
- **Sin secretos propios del plugin ni CVE de dependencias:** el único secreto es el informe de mayo
  versionado (I6), no código del plugin; trivy no halló CVE (el plugin no vendoriza dependencias con
  versión).
- **Requisitos de despliegue correctos del manual gobernante:** §1.1 (no Docker/composer) y §10.2
  (qué NO copiar: 31 MB → 412 KB) verificados ciertos y útiles.
