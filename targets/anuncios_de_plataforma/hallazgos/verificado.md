Comprobado y correcto, con la evidencia que lo respalda.

| Qué se verificó | Resultado | Cómo se comprobó |
|---|---|---|
| **No hay inyección SQL en la resolución de cursos** | Correcto | semgrep marcó `tainted-callable` en `preview_correo.php:196` y `send_segmented.php:147`. Se leyó el código: la línea es `$stmt->execute()` de una sentencia preparada. El `$sql` se arma con `str_replace` de `__RGN_IN__`/`__CENTRO_IN__`/`__CODE_IN__`, pero `pdo_in_clause` (`lib/helpers.php:119`) genera **marcadores nombrados**, no valores, y las entradas pasan antes por `intval` o `^\d+$`. Los valores van ligados. |
| **Todos los puntos de entrada validan sesión y permiso** | Correcto | Se revisaron los 17 uno a uno. Quince usan los envoltorios del plugin; `ajax/categories.php` hace `isloggedin()`+`has_capability` en línea; `active_role_users.php` usa `require_login`+`require_capability`+`confirm_sesskey`. Los tres idiomas son correctos. |
| **CSRF en los endpoints que mutan estado** | Correcto | `checkCsrfToken` (envoltorio de `confirm_sesskey`, con validación de tipo) está en `insertRecord`, `updateRecord`, `deleteRecord`, `order`, `ajax/send_segmented`, `ajax/preview_correo` y `ajax/saved_filters`. Los de solo lectura no lo llevan, que es lo correcto. |
| **Defensa anti-CSRF adicional en el envío masivo** | Correcto y deliberado | `ajax/send_segmented.php:44-48` rechaza con 415 todo `Content-Type` que no sea `application/json`, lo que impide dispararlo desde un formulario HTML plano. |
| **`checkUserRole` falla cerrado** | Correcto | Su parámetro `$requiredLevel` tiene por defecto `'edit'`, el nivel más restrictivo: olvidarlo deniega, no concede. |
| **La cookie de sesión está bien configurada** | Correcto | `MoodleSessionzajuna` se emite con `secure` y `HttpOnly` (verificado por cabecera). Las alertas de ZAP sobre cookies sin esos atributos corresponden a la portada institucional, no al plugin. |
| **El Swiper del carrusel fija versión y verifica integridad** | Correcto | `slider/lib/showSlider.php:224-229` carga `swiper@12.2.0` con `integrity=sha384-…` y `crossorigin`. El comentario del código demuestra que la decisión fue consciente. (La copia de respaldo `showSlider_7_noviembre.php` no lo hace — ver §3.7.) |
| **La alerta de inyección SQL de ZAP es un falso positivo** | Confirmado | Re-verificado contra **este** despliegue, no heredado de la ronda anterior: `' AND '1'='1'`, `' AND '1'='2'` y un valor inocuo devuelven cuerpos idénticos byte a byte (23.344 B) tras normalizar los tres nonces por petición. El parámetro `anchor` ni siquiera se refleja. |
| **El plugin no envía correo por su cuenta** | Confirmado | No hay `email_to_user`, `message_send` ni `mail(` en el repositorio: `send_segmented.php` hace `INSERT` en `midb.envios2` y termina. La entrega la hace un proceso externo. |
| **Los dos plugins se registran correctamente en Moodle** | Correcto | Tras `admin/cli/upgrade.php`: `mdl_local_slider` creada, seis filas de configuración sembradas, y las dos capabilities registradas en contexto sistema con `riskbitmask=20` (RISK_SPAM\|RISK_XSS), tal y como declara `db/access.php`. |
| **Las migraciones 005–013 son correctas** | Correcto | Reanudadas tras salvar el bloqueo de la 004, las diez restantes pasan sin un solo error y dejan el esquema exactamente como predice §8.4: 34 regionales, 118 centros, las cinco columnas multivalor en `text`, `envios2.cursos` en `jsonb`. |

### Autorización — medida por fin, recorriendo el flujo con dos cuentas reales

Tras conceder las capabilities al rol `manager` (§10.3 del `DEPLOY.md`, paso obligatorio que la
instalación no hace sola), se recorrieron las pantallas con dos cuentas de privilegio distinto sobre el despliegue local,
verificando cada resultado por CÓDIGO **y por CUERPO** (un 200 con un JSON `nopermissions` es una
denegación, no un acceso): `qa_slider_alto` (rol `manager`, con `:view` y `:edit`) y
`qa_slider_bajo` (rol `student`, sin ninguna de las dos).

| Recurso | Privilegio ALTO | Privilegio BAJO | Veredicto |
|---|---|---|---|
| `index.php` | 200 «Cargar Imagen» | 303→login | deniega |
| `menu.php` | 200, carga el hub | 303→login | deniega |
| `segmented.php` | 200, formulario completo | 303→login | deniega |
| `show_order.php` / `manage_images.php` | 200 con contenido | 303→login | deniega |
| `ajax/categories.php?action=modalidades` | 200 con datos | **403** | deniega |
| `active_role_users.php` (nombres+correos) | — | 200 con JSON `nopermissions` (no entrega datos) | deniega |
| `send_logs.php` | 404 por esquema incompleto (§3.3) | 303→login | deniega |

**No se encontró ningún salto de autorización.** La cuenta de privilegio bajo no alcanzó ningún
recurso reservado, ni por página ni por endpoint AJAX. Los envoltorios propios del plugin hacen
lo que su código dice que hacen.

> **Esta dimensión es NO AUTORITATIVA**, y la razón importa: las dos cuentas las creó QA con la
> CLI de Moodle el 19-ago-2026 (con roles preexistentes, `manager` y `student`, sin inventar
> ninguno). Un permiso mal puesto en producción es invisible para una cuenta creada cinco
> minutos antes. Para una medida autoritativa hacen falta dos cuentas del entorno real,
> entregadas por el equipo. Lo que sí queda demostrado es que **el mecanismo funciona**.

### Carga (k6) — rendimiento holgado, con una lección de método

Prueba autenticada de solo lectura, rol alto, 5 usuarios concurrentes durante ~70 s:

| Métrica | Resultado | Umbral |
|---|---|---|
| Error | **0,00%** (0 de 936 peticiones) | < 1% |
| Latencia p95 | **73 ms** | < 1500 ms |
| Comprobaciones | 1608 de 1608 correctas | — |

La primera corrida marcó **19,63% de error**, que se parecía a un sistema inestable. No lo era:
el desglose mostraba cuatro pantallas al 100% de éxito y `table_logs.php` al 0% (0 de 218). El
guion de carga llamaba a esa ruta sin sus dos parámetros obligatorios — era un defecto del
guion, no de la aplicación (queda en la bitácora interna, L-R2-07). Retirada esa ruta, el
resultado real es el de la tabla. Es el mismo patrón que METODOLOGIA §4 usa de ejemplo, y la
señal que lo delató fue el `0% — ✓ 0 / ✗ 218`: una degradación real casi nunca es exactamente 0%.

**Responsable de dar por buenas estas verificaciones:** QA (esta auditoría). Ninguna requiere
acción del equipo de desarrollo.
