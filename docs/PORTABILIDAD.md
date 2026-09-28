# Portabilidad del entorno "MANUALES DE DESPLIEGUE WITH REPORT"

> Cómo mover TODO el flujo de revisión de proyectos a otro PC. La idea central: el entorno son
> **51 GB**, pero solo **~2 MB son código versionable**; el resto es dato pesado o estado de la
> máquina que **se reconstruye, no se copia a git**. Este documento dice qué va a cada sitio.

Fecha: 2026-08-31. Se escribe desde SECURITY-LAB (que sí se versiona) pero describe todo el árbol.

## El principio: 3 capas por naturaleza

| Capa | Qué es | Tamaño | Dónde vive | En el PC nuevo |
|---|---|---|---|---|
| **1. Código del lab + perfiles** | `SECURITY-LAB/` (Makefile, tools, lib, recipes, `targets/*`: guiones, riesgos, hallazgos) | **~2 MB** (233→272 archivos) | **git** (`github.com/Zlioz8/QA-harness`, y opcional tu GitLab) | `git clone` |
| **2a. Entregables** | Informes + COTEJO + `mcp-evidencia/*.png` + baselines de evidencia | ~98 MB | **git con LFS** (repo aparte) o disco externo | clone LFS / copiar |
| **2b. Datos pesados** | `INFRALOCAL/` (VMs), `ZAJUNA NGINX/` (backups `.zip`/`.mbz`, dumps), `node_modules/`, `vendor/` de los workspaces | **~40 GB** | **USB / disco externo. NUNCA git** | copiar de la USB / reinstalar |
| **3. Estado de la máquina** | Core Zajuna (PostgreSQL `moodle`, nginx, php-fpm, `/var/www`), Docker, llave SSH, `target.env.local`, `/etc/hosts` | (sistema) | **se reconstruye** | ver §"Arranque en PC nuevo" |

## ¿Cabe en GitLab?

- **El laboratorio (capa 1): sí, trivialmente.** 2 MB. Entra en cualquier namespace (GitLab.com,
  o tu personal en `git.fsrisaralda.com`). Límite típico GitLab.com free: 10 GB por proyecto — sobra.
- **Los entregables (capa 2a) con LFS: sí.** ~98 MB, mejor por Git LFS porque son `.png`/`.html`
  binarios. Van en un repo APARTE (p.ej. `QA-entregables`) para no mezclar binarios con el código.
- **Los 51 GB completos: no, ni deben.** Las VMs y los dumps rompen cualquier cuota de git y git
  es pésimo con binarios de gigas. Esos van a disco externo.

## Estado actual de QA-harness (validado 2026-08-31)

- Rama local `feat/adi-contrato-despliegue`, sigue a `origin/version2`, **3 commits por delante**
  (NO empujados). El último commit (`cccff33`) trae todo el trabajo de las rondas #2–#8.
- **Pendiente de empujar** cuando decidas el remoto: `git push origin feat/adi-contrato-despliegue`
  (y/o añadir tu GitLab: `git remote add gitlab <URL>` + `git push gitlab feat/adi-contrato-despliegue`).
- `.gitignore` auditado: fuera quedan `work/`, `reports/`, `target.env.local`, `targets/*/deps/*.env`
  (creds sandbox), `baselines/core-*/` (config del core), `node_modules`, dumps. Sin secretos ni
  binarios en los commits.

## Qué NO está en git y hay que llevar aparte (secretos y estado)

1. **Llave SSH de la fábrica:** `~/.ssh/id_ed25519_fsrisaralda` (+ `~/.ssh/config`). Sin ella no se
   clonan los repos de `git.fsrisaralda.com`. Llévala en la USB cifrada / gestor de secretos.
2. **`targets/*/target.env.local`** — las credenciales reales de cada proyecto (cuentas, URLs,
   tokens). Gitignored a propósito. Cópialas aparte (están en `SECURITY-LAB/targets/*/`).
3. **Los repos clonados** bajo cada workspace (p.ej. `CENTRO DE CALIFICACIONES/centro_de_*`): NO se
   copian, se **re-clonan** de la fábrica con la llave SSH.
4. **Los manuales sueltos** de cada workspace (`.md`/`.docx` entregados fuera de repo): pequeños;
   cópialos al disco externo o a `QA-entregables`.

## Reconstrucción del core Zajuna (la dependencia local grande)

El flujo se alimenta de un ZAJUNA bare-metal (PostgreSQL `moodle` 4.8 GB con tablas `mdl_*`, nginx
bajo `nginx.zajuna.com`, php-fpm 8.1, wwwroot `/var/www/zajuna`). No se copia: se **restaura desde
los dumps de la USB**. Insumos presentes en la USB (`/media/zlioz/zlioz`):

- `html27022026l.zip` (10.7 GB) → `/var/www/html`.
- `zajunadata27022026.zip` (769 MB) → moodledata.
- `zajunadb.dump` (127 MB) → `pg_restore` a la BD `moodle`.
- `zajuna27022026.zip`, `dump-zajuna_dash-*.zip` → variantes/otras BDs.

Procedimiento detallado: **`INFRALOCAL/MANUAL_UNIVERSAL_DESPLIEGUE.md`** y `INFRALOCAL/RESUMEN_MAESTRO.md`
(ya existen). Ese manual es la fuente de verdad para levantar el core; este documento solo lo enmarca.

## ANTIPLAGIO — migrado al harness (2026-08-31)

El workspace `ANTIPLAGIO/` son **6,2 GB**, de los que solo ~700 KB son conocimiento. Repartido
según las tres capas de arriba:

| Qué | Tamaño | Dónde queda |
|---|---|---|
| Auditoría, contexto, despliegue, escenario (corpus + `cli/` + guion), entorno local | ~700 KB | **git**, en `targets/antiplagio/` |
| Credenciales reales de local y preprod + token de Winston | — | `targets/antiplagio/target.env.local` (**gitignored**, USB) |
| Capturas de evidencia (`*.png`) del escenario y las verificaciones | ~3 MB | **USB** / QA-entregables |
| `04-pruebas-y-material/` (75 docx, 38 pdf, 215 log, 438 yml) | **5,8 GB** | **USB.** Nunca git |
| `03-documentacion-proyecto/` (SARIF de Qodana, documentación heredada) | 459 MB | **USB** |
| Escenario montado en el Moodle local (EV-A/B/C/W, BD) | — | **se reconstruye**: `escenario/cli/*.php` |

Punto de entrada en el PC nuevo: **`targets/antiplagio/CONTEXTO.md`** (estado, decisiones y qué
quedó abierto) y **`targets/antiplagio/hallazgos/orden.md`** (qué hacer primero). El detalle
completo de la auditoría está en `hallazgos/auditoria-completa.md`.

### Copiado a la USB el 2026-08-31

Decisión del responsable: **en la USB va todo, credenciales incluidas.** No es lo mismo que git
—ahí sigue pendiente decidir— pero la USB es soporte físico propio y se prioriza no perder nada.
Guía de orientación escrita en `AUDITORIAS-QA-ZAJUNA/ANTIPLAGIO/LEEME-PRIMERO.md`.

| Copiado | Detalle |
|---|---|
| Workspace `ANTIPLAGIO/` | La copia previa era del 28/08; se actualizó con todo lo del 31 |
| `SECURITY-LAB/` | Incluye `targets/antiplagio/` completo **y** `target.env.local` |
| `ANTIPLAGIO/_repo-codigo/antiplagio/` | El repo con su `.git`. **Destino real: `~/proyectos/antiplagio`**, no el workspace: de esa ruta depende el bind mount de `/etc/fstab` |
| `..._repo-codigo/*.bundle` | Historial en un fichero, por si el `.git` sufre en exfat |
| `..._repo-codigo/env-del-devops-b3957dd/` | Los 8 `.env` del commit huérfano, extraídos a texto plano |

> **`b3957dd` es frágil y solo existe aquí.** Ninguna rama lo apunta (force-push sobre
> `mq5preproduccion`), así que un `git gc` puede borrarlo y `git bundle --all` no lo empaqueta.
> Contiene los `.env` con `WINSTON_TOKEN`, `DB_PASSWORD` y `OWNER_PASSWORD` reales. En el PC
> nuevo: `git tag rescate-mq5-devops b3957dd` para que deje de ser huérfano.

> **Espacio:** la USB quedó al 98 %. Hubo que vaciar `.Trash-1000` (761 MB) para que cupiera el
> material de pruebas. El aviso de higiene de más abajo sigue vigente y ahora es urgente: para la
> próxima migración hace falta un disco mayor.

> Lo que **no** viaja y hay que aceptar: la sesión de Claude y su memoria. Por eso todo lo que
> estaba solo ahí se volcó a `CONTEXTO.md`. Si algo importante no está en un `.md`, se pierde.

## Arranque en PC nuevo — checklist

```
1. Instalar: git, git-lfs, docker + compose, postgresql-client, php-cli.
2. Restaurar secretos:
   - ~/.ssh/id_ed25519_fsrisaralda (+ config)  [de la USB cifrada]
   - targets/*/target.env.local                 [de la USB]
     (antiplagio incluido: sin él no hay cuentas de Moodle ni token de Winston.
      La plantilla versionada targets/antiplagio/target.env.local.example dice qué rellenar)
3. git clone https://github.com/Zlioz8/QA-harness.git SECURITY-LAB
   (y tu GitLab si añadiste espejo)
4. git clone <QA-entregables> con LFS           [entregables, capa 2a]
5. Copiar de la USB los datos pesados (INFRALOCAL/, ZAJUNA NGINX/) al disco del PC nuevo.
6. Restaurar el core Zajuna desde los dumps      [INFRALOCAL/MANUAL_UNIVERSAL_DESPLIEGUE.md]
7. Por cada proyecto a auditar: re-clonar sus repos bajo su workspace (SRC_PATH).
8. Verificar:  make doctor TARGET=<perfil>       (avisa de core caído, puertos, ramas).
```

## Aviso de higiene (pre-existente, no bloquea la migración)

- La USB está al **94 % (7 GB libres)** con una copia desactualizada + VMs. Para una migración
  limpia conviene un disco externo mayor, o podar `.Trash-1000` y duplicados.
- `targets/movil/target.env` (gitignored, NO en el commit) tiene en disco un `SONAR_TOKEN=squ_…` y
  contraseñas reales. Antes de compartir esa carpeta, mueve esos valores a `target.env.local`.
  `targets/antiplagio` y `targets/costos_web` (ya en historia) traen contraseñas de laboratorio
  (`Lab-Test-2026!`, `admin01`): son fixtures, pero conviene migrarlas a `.local` también.
