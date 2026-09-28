# Hardening del Laboratorio de Auditoría (SECURITY-LAB)

**Objeto:** revisar la seguridad de la **herramienta** que usamos para auditar (no del proyecto
Costos Web), determinar hallazgos y endurecerla. La ironía es real: una herramienta que restaura la
**base de datos con PII de 20.368 personas** debe cuidarse tanto como el sistema que audita.
**Fecha:** 24 de julio de 2026. **Host de la corrida:** `10.217.78.121` (en LAN institucional).

---

## Resumen

| # | Hallazgo del laboratorio | Sev. | Estado |
|---|--------------------------|------|--------|
| L1 | PII real expuesta en la LAN (puertos en `0.0.0.0` + credenciales de prueba conocidas) | 🔴 Crítico | ✅ **REMEDIADO** |
| L2 | `~/.ssh` completo montado en el contenedor de clonado | 🟠 Alto | Pendiente |
| L3 | Imágenes de herramientas fijadas a `:latest` (mutables) | 🟠 Alto | Pendiente |
| L4 | `APP_DEBUG=true` en el runtime del lab | 🟡 Medio | Pendiente |
| L5 | `reports/` con permisos `777` en el host | 🟢 Bajo | Aceptable |
| L6 | `network_mode: host` en Playwright | 🟢 Bajo | Aceptable |

---

## L1 · 🔴 PII real expuesta en la LAN — REMEDIADO

### Qué estaba pasando
Los servicios publicaban puertos con la sintaxis `- "8100:80"`, que en Docker Compose **bindea a
`0.0.0.0`** (todas las interfaces), no solo a `localhost`. Como el laboratorio restaura el **dump
real** (20.368 personas) y siembra cuentas de prueba con **credenciales conocidas**
(`admin@test.local` / `secret123`), cualquiera en la red institucional podía entrar.

### Evidencia (verificada en vivo)
```
# desde la IP de LAN del host:
curl http://10.217.78.121:8100/up                 -> 200
POST /api/login  admin@test.local / secret123     -> 200   (¡acceso admin desde la LAN!)
```
Un tercero en la red podía autenticarse como administrador y **extraer los 20.368 registros con datos
personales** a través de la herramienta de auditoría.

### Remediación aplicada
Se bindearon **todos** los puertos publicados a `127.0.0.1` en `docker-compose.yml`:
```yaml
ports:
  - "127.0.0.1:${PROD_PORT:-8100}:80"   # antes: "${PROD_PORT:-8100}:80"
  # idem app (8000, APP_PORT), frontend (5173), sonarqube (9000)
```
**Verificado tras el fix:** `127.0.0.1:8100/up` → 200; `10.217.78.121:8100/up` → **000 (bloqueado)**.
La PII deja de ser accesible desde la red.

---

## L2 · 🟠 `~/.ssh` completo montado en el contenedor de clonado

### Qué está pasando
El servicio `clone` monta **toda** la carpeta de claves del usuario:
```yaml
volumes:
  - ${HOME}/.ssh:/root/.ssh:ro
image: alpine/git:latest
```
Entrega las **claves privadas SSH del usuario** (todas, no solo una de despliegue) a un contenedor
basado en una imagen `:latest` (mutable, ver L3). Una imagen comprometida podría **exfiltrar todas
las claves**.

### Cómo solventarlo
- Usar una **clave de despliegue dedicada de solo lectura**, montada como archivo único:
  `- ./deploy_key:/root/.ssh/id_ed25519:ro` (y solo esa).
- O usar **agente SSH** (`SSH_AUTH_SOCK`) en lugar de montar claves.
- O clonar en el host (fuera de contenedor) y montar solo `work/` — el lab ya soporta esta vía en el
  README.

---

## L3 · 🟠 Imágenes de herramientas en `:latest`

### Qué está pasando
`alpine/git`, `grafana/k6`, `sonar-scanner-cli`, `qodana-php`, `gitleaks`, `trufflehog`,
`zap-stable` usan tag `:latest`. Es **mutable**: un tag republicado (o comprometido) se ejecuta con
los montajes del lab — incluido `~/.ssh` en el caso de `alpine/git` (ver L2). Riesgo de cadena de
suministro.

### Cómo solventarlo
Fijar por **digest** (`imagen@sha256:...`) las imágenes de herramientas, y actualizarlas de forma
controlada. Al menos las que reciben montajes sensibles (`clone`).

---

## L4 · 🟡 `APP_DEBUG=true` en el runtime del lab

### Qué está pasando
`docker/lab.env` y el servicio `app` corren con `APP_DEBUG=true`. Combinado con la exposición de red
(ya remediada en L1), habría filtrado trazas y datos en los errores. Es útil para depurar la
auditoría, pero conviene apagarlo salvo cuando se necesite.

### Cómo solventarlo
`APP_DEBUG=false` por defecto en `lab.env`; activarlo puntualmente con una variable de entorno cuando
se investigue un fallo.

---

## L5 · 🟢 `reports/` con permisos `777`

Se abrieron permisos de `reports/` para que herramientas con distinto UID (ZAP, Trivy) pudieran
escribir. Es una carpeta local de salida, sin datos sensibles del negocio. **Aceptable**; si molesta,
usar `user:` en los servicios o `chown` posterior.

## L6 · 🟢 `network_mode: host` en Playwright

Necesario para que el navegador resuelva la URL hardcodeada del SPA (`localhost:8000`, hallazgo H17
del proyecto). Solo aplica al perfil `e2e` y a imagen oficial de Microsoft. **Aceptable**; alternativa
sería una red dedicada con alias.

---

## Buenas prácticas que el lab ya cumple

- **Proyecto montado *read-only*** (`:ro`): la auditoría nunca modifica el código objetivo.
- **Base de datos efímera**: se destruye con `make down -v`, sin residuos.
- **Sin contenedores privilegiados**, sin montar el socket de Docker, sin `cap_add`.
- **Generador de carga aislado** (k6 en contenedor aparte), que no contamina las mediciones.
- **Herramientas dedicadas** por dimensión, con su config nativa (sin lógica en scripts sueltos).

---

## Acciones pendientes (prioridad)

1. **L2/L3 juntos:** clave de despliegue dedicada + fijar por digest la imagen de `clone`. Cierra el
   riesgo de robo de claves por cadena de suministro.
2. **L4:** `APP_DEBUG=false` por defecto.
3. Documentar en el README que el lab **debe correr solo en `localhost`** y nunca en un host con
   puertos abiertos a la red mientras contenga la PII real.

*Remediación L1 aplicada y verificada en esta sesión. El resto queda documentado para el
mantenimiento del laboratorio.*
