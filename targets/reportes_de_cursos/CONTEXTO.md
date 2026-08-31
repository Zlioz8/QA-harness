# CONTEXTO — reportes_de_cursos (ZAJUNA Early Alert)

> Léelo con `make brief TARGET=reportes_de_cursos`. Aquí va solo lo que no está en ningún artefacto.

## Estado en una frase

**R1 CERRADA (GATE FAILED), 2026-08-21 — LABORATORIO COMPLETO.** Todas las dimensiones aplicables
ejecutadas: estático, contrato despliegue+API, DAST (ZAP 23), **k6 0% error p95 5,5 ms**, **matriz
Playwright 6/6**, MCP. api-fuzz NO CONCLUYENTE (L-R4-05), Qodana NO DISPONIBLE (pago). Denegación
del aprendiz AUTORITATIVA en el servidor; matriz completa visualizada en local (capturas). Informe
0 huecos. Único ⟨PENDIENTE⟩ R2: caso positivo con instructor REAL (las 5 entregadas CADUCADAS).

NOTA para R2: target.env.local quedó con las cuentas LOCALES (qa_zea_teacher/student, curso 9708)
y APP_INTERNAL_URL=https://nginx.zajuna.com para la corrida live local. Las cuentas del servidor y
sus cursos están en el comentario de target.env.local y en mcp/journeys.md. compose.runtime.yml da
a k6/api-fuzz/zap el extra_host nginx.zajuna.com (Moodle valida HTTP_HOST).


## Decisiones tomadas, con su razón

- **Nombre real: ZAJUNA Early Alert**, no «Reportes de Cursos». Plugin Moodle
  (`block_zajuna_early_alert`, PHP) + API Go (`zea-api`) + SPA Vue (`vue-app`). La carpeta engaña.
- **Rama auditada: `dev`.** Existe hoy (el prompt decía que no) y trae el `DEPLOY.md` (818 líneas,
  2026-08-20). `SEGUIMIENTO_QA_FABRICA.md` apunta a `docs/despliegue_demo.md` porque su foto es del
  19/08, anterior a `dev`. **Corregir esa fila** al cerrar.
- **Segundo repo `reportes_de_curso`: NO clonado.** Legacy, fuera de alcance (operador QA, 21/08).
  Declarado en el perfil, va a RUN.md y al informe.
- **`AUTH_ADAPTER=zea-standalone`**, adaptador NUEVO para las dos mitades del laboratorio
  (`lib/auth/index.ts`, `lib/k6/session.js`). Login en DOS saltos: `login.php` (JWT identidad) →
  `token.php?courseid=N` (JWT de curso, el que acepta la API). Un 403 en token.php es un DATO de la
  matriz (aprendiz sin `viewreports`), no un fallo — el adaptador lo trata así.
- **nginx del core: se AÑADEN dos `location`, no se corre `install-nginx.sh`.** `/` es un CMS y
  Moodle vive bajo `/zajuna`; el script reescribiría el site y tumbaría el CMS y el despliegue de
  #3. Ver `SECURITY-LAB/PUERTOS.md`.

## Contra qué se está midiendo

- Estático: rama `dev` @ `ef3493bd`, clon local en el workspace.
- Vivo: PENDIENTE. Plan: medir primero en LOCAL (nginx del core + compose del repo) y CONFIRMAR
  contra `https://zajunavideo5.com` (ya sirve `/zea-api` y `/zea-dashboard`).
- Cuentas: entregadas por el operador (4 instructores por ficha + 1 aprendiz). Aún NO en
  `target.env.local`. Con ellas, la matriz contra el servidor es AUTORITATIVA.

## Hallazgos ya con evidencia (a triar / confirmar en vivo)

- **`/zea-api/metrics` público en internet** en el servidor: 200, 15 KB, sin JWT. DEPLOY.md §17 lo
  da por seguro «porque escucha en loopback»; por el proxy sale. Confirmado por curl y por la regla
  `zea-solo-salud-es-publica` de Spectral.
- **Incongruencia de contrato**: `openapi.json` declara la URL de producción `/api-zea`; el nginx
  del repo publica `/zea-api/`. `/api-zea/health` en el servidor devuelve 200 con el HTML del CMS.
- **Clave privada RSA en la historia**: `analitica-predictiva-backend-main/jwt_private.pem`
  (huella pública md5 `9112fb63…`). Añadida en `0de675c4`, borrada en `d8b8bf69`; NO en rama viva.
  Es de un backend PREDECESOR. **Pendiente**: confirmar que NO es la clave con la que firma
  `token.php` hoy (si lo fuera, crítico).
- **`.env.production` versionado**: único hallazgo del contrato. Contenido: una línea
  `VITE_API_BASE=/zea-api`, sin secretos. Severidad la decide el triaje (probable bajo).
- Sonar 986 · semgrep 29 · trivy-fs 1 (`GO-2026-5932`) · gitleaks 12 — sin triar.

## Defectos del laboratorio corregidos (en BITACORA)

- `make ingest-deploy`: 4 hallazgos → 3 eran del laboratorio (grep+pipefail «sin CI»; lock
  solo-npm; `php.ini` citado-para-negarlo). Corregidos en `tools/ingest-deploy.sh` → quedó 1 real.
  L-R4-01/02/03.
- Spectral: `spectral:oas` no valida OpenAPI 3.2 → 14 `oas3-schema` falsos; las reglas propias sí.
  L-R4-04.

## Lo que quedó abierto

- [ ] Cuentas + `ZEA_COURSE_A/B` + `BASE_URL`/`HEALTH_PATH` en `target.env.local`.
- [ ] Baseline del core (`baselines/core-moodle-precambios-<fecha>/`) ANTES de desplegar.
- [ ] Desplegar local por DEPLOY.md §15; añadir 2 `location` a `zajuna.conf` (NO install-nginx);
      `VITE_MOODLE_BASE=/zajuna` en `.env` ANTES de compilar.
- [ ] `make live` local → confirmar contra `zajunavideo5`. MCP: tablero, detalle aprendiz, vista
      previa de notificación (en #3 el preview reveló un 502).
- [ ] Triaje, `make gate run-manifest`, `make informe`.
- [ ] Confirmar si el `jwt_private.pem` de la historia es la clave de firma actual.

## Lo que NO se midió, y por qué

- Qodana: PHP y JS son imágenes de pago, sin `QODANA_TOKEN` → NO DISPONIBLE (no es no-aplicable:
  por eso no está en GUION_NO_APLICA). Calidad la cubren Sonar + semgrep.
- `GUION_NO_APLICA=jmeter,device,mobsf,trivy-image` — cada uno con su razón en el perfil.
