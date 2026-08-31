# Guion de flujos de navegador (MCP) — analitica_notificaciones

Flujos REALES del usuario a recorrer con el servidor MCP del navegador, en LOCAL
(`http://localhost:8089`) y en el SERVIDOR de pruebas (`https://zajunavideo5.com/analitica`).
Cada flujo declara qué hallazgo del informe contrasta.

- **F1 · SSO por el plugin.** En Moodle, entrar por `local/reporteszajuna/redirect.php` → observar
  la redirección 302 con `?token=<wstoken>` en la URL (contrasta §3.6/§3.3) y que el JWT queda en
  `localStorage` (`rz_token`).
- **F2 · Denegación por rol.** Entrar con una cuenta `student` (capacidad PREVENT) → debe recibir
  403 «Sin permiso» (contrasta la matriz de autorización).
- **F3 · Catálogo y cabeceras.** Cargar la home de reportes → 10 reportes; comprobar por `fetch`
  las cabeceras de seguridad (CSP/X-Frame/HSTS/X-Content-Type) — deben faltar (contrasta §3.7).
- **F4 · 404 inexistente.** Pedir una ruta inventada → debe ser 200 con el SPA (contrasta §3.5,
  catch-all).
- **F5 · Vista previa.** Seleccionar `registro_usuarios` → «Vista previa» → observar el resultado
  (contrasta §3.12: 502 en producción / error de esquema en un Moodle limpio).
- **F6 · Generar y descargar.** Generar un reporte pequeño → «Mis Solicitudes» → verificar
  transición a FINALIZADO y descarga.
- **F7 · Propiedad (IDOR).** Con una segunda cuenta, intentar leer la solicitud de otra → 403
  (contrasta la matriz de autorización).
- **F8 · Programados.** Listar/crear una programación → verificar que queda «Activo» con próxima
  ejecución.

Evidencia (URL, resultado, logs de consola/red por flujo) → `reports/<t>/mcp/journeys.md`.
