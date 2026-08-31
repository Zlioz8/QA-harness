Lo que se comprobó y salió **bien** — se registra para que conste que se miró, no solo lo que falló:

- **El servidor web es real, no `artisan serve`.** El Dockerfile es `php:8.2-apache`, entrypoint
  `apachectl -D FOREGROUND`. El manual acierta y el despliegue lo cumple. *(Anderson Rincón)*
- **Las migraciones son fail-closed.** El servicio `migrate` con `condition:
  service_completed_successfully`: cuando falló (D1), bloqueó el arranque de `app`/`worker` en vez
  de servir con un schema a medias. Es exactamente lo que el manual promete. *(Anderson Rincón)*
- **Worker y scheduler bien planteados** como procesos de larga vida separados; el `indexer`
  (índices CONCURRENTLY en segundo plano) no bloquea el arranque, como el manual describe. *(Anderson Rincón)*
- **La superficie pública resiste el path-traversal.** `/api/storage/images/{f}` y
  `/api/editor-images/{f}` reciben el nombre de la URL; los intentos `../../etc/passwd` dan
  400/404, nunca 200 con un fichero del sistema. Verificado a mano y por el spec de mecanismos. *(Anderson Rincón)*
- **La descarga firmada valida la firma:** sin firma → 403. *(Anderson Rincón)*
- **El limitador de login está activo:** `throttle:login` 5/min, cabecera `X-RateLimit-Limit: 5`.
  Anti fuerza-bruta funcionando. *(Anderson Rincón)*
- **El cerco del aprendiz es una lista blanca de 3 rutas** (`EnsureAprendizAcotado`): todo lo demás
  es 403 con mensaje explícito. Diseño de autorización sólido y legible (pendiente de validar con
  cuentas reales cuando se desbloquee el SSO). *(Anderson Rincón)*
- **El SSO no filtra el motivo del rechazo** (evita el oráculo para un atacante) y el parámetro
  `encuesta` es un entero (no permite redirect abierto). Manejo de errores ejemplar. *(Anderson Rincón)*
- **El fallback de la SPA a producción está bien hecho:** recuerda el origen real de quien entró
  desde el LMS y fija la dirección de vuelta desde el backend, no desde la URL —cerrando de raíz un
  redirect abierto. Frontend maduro. *(Anderson Rincón)*
- **Los 4 sinks `dangerouslySetInnerHTML` de la SPA están saneados:** los 7 llamantes usan
  DOMPurify/sanitizeHTML. Los avisos de XSS de semgrep son falsos positivos de sink. *(Anderson Rincón)*
- **La API responde sana bajo carga ligera:** k6 p95 178 ms, 0 % de error de disponibilidad (5xx),
  y el limitador corta con 429 (no 5xx) bajo ráfaga. *(Anderson Rincón)*
- **Sin secretos vivos:** de los 3 secretos en la historia (todos en `encuestas_backend`),
  TruffleHog verificó 0 como activos. gitleaks sobre el repo `encuestas` (la SPA) dio cero — su log
  reporta 941 commits recorridos y ~100 MB escaneados. *(Anderson Rincón)*
