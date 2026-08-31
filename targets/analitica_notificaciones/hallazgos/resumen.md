**El sistema funciona y responde bien, pero no está en condiciones de considerarse seguro ni
correctamente desplegado tal como está hoy.** El despliegue vivo autentica, sirve sus pantallas y
soporta carga sin errores (p95 ≈ 190 ms, 0 % de fallos), así que el problema no es de estabilidad
sino de tres bloques concretos. Es la primera ronda: ningún hallazgo arrastra historial todavía.

**1. La sesión se puede forjar por dos caminos independientes.** La clave HS256 con la que la
aplicación firma sus JWT está versionada en claro en el `.env` del repositorio (§3.1), y la
librería que verifica esos JWT (`python-jose` 3.3.0) tiene una vulnerabilidad crítica de
confusión de algoritmo (§3.2). Cualquiera de las dos, por separado, permite fabricar una sesión
válida de cualquier usuario. Y hay un tercero: el propio wstoken de sesión del SSO se genera en `redirect.php` con
`md5(uniqid(rand()))` (§3.3) — **predecible**, adivinable acotando el instante de emisión — y
viaja en la URL, quedando además en `localStorage` (§3.6). Tres caminos distintos a una sesión ajena.

**2. El repositorio expone credenciales reales y no se despliega limpio.** Además de la clave de
sesión, el `.env` versionado trae contraseñas de base de datos, y la conexión a Moodle usa el
superusuario `postgres` donde debería bastar solo lectura (§3.10). No hay `.env.example` ni
integración continua (§3.8): el hueco de configuración se tapó, de hecho, versionando el secreto.

**3. Hay superficie que no está donde el equipo cree.** El router de administración nunca se monta
y, por un catch-all, `/api/admin/users` —y cualquier ruta inventada— responde 200 con el frontend
en vez de 404 (§3.5): no existe el 404 en toda la aplicación. La revalidación de sesión contra
Moodle es *fail-open*: si esa base falla, toda sesión se da por válida sin comprobar (§3.9).

**4. Recorrer la interfaz en el navegador reveló lo que ninguna herramienta automática vio.** La
vista previa del reporte más usado devuelve un **502 crudo** en producción en vez del error
controlado que documenta el manual (§3.12), y los reportes dependen de un esquema de base de datos
(`midb`) y de tablas de plugins que **no están documentados** — un servidor nuevo con un Moodle
limpio no genera ni un reporte, y el rol de solo lectura recomendado no basta (§3.13). La
generación asíncrona, en cambio, funciona correctamente.

Sobre el método de esta ronda, dos cosas que condicionan cómo leerla. La **autorización se midió contra un
despliegue local** montado sobre el core Moodle de la máquina, porque la segunda cuenta entregada
(`comunidades1`) no obtiene token del web service en producción. El control funciona: un rol bajo
(`student`) es denegado con 403 y una cuenta no puede leer las solicitudes de otra (IDOR → 403).
Aviso importante: esas cuentas de prueba las creó el laboratorio, así que la medición **no es
autoritativa** sobre las asignaciones de rol reales de producción — para eso hace falta una cuenta
REAL de bajo privilegio con acceso a reportes. Y el **escaneo activo llegó
al login y a la superficie estática, no a los endpoints con sesión**, porque requieren token: la
ausencia de inyección/SQLi en el informe se refiere a lo alcanzado sin autenticar, no a toda la API.
