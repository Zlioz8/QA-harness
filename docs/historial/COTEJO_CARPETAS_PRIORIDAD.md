# Cotejo — carpetas de `MANUALES DE DESPLIEGUE WITH REPORT/` contra `Lista de prioridad - QA.xlsx`

> **Propuesta, no ejecución.** No se ha renombrado ni movido nada. `targets/antiplagio`,
> `targets/movil` y `targets/costos_web` tienen `SRC_PATH` apuntando a estas carpetas: un `mv`
> los rompe en silencio, y el síntoma aparecería muy lejos de la causa. Decide tú qué se aplica.
>
> Fecha: 19-ago-2026. Repos verificados con `git ls-remote` contra
> `git.fsrisaralda.com:2222/fabrica_zajuna/`.

## Por qué se hizo este cotejo

El encargo de esta sesión llegó mezclando datos de tres filas distintas de la lista (una
prioridad, la URL de otra y el nombre de perfil de una tercera), y la carpeta local indicada no
correspondía al proyecto. No fue un descuido aislado: **los nombres de las carpetas no siguen los
de la lista**, y en un caso dos prioridades distintas conviven dentro de la misma carpeta.

## El choque que provocó la confusión

**`ANUNCIOS/` contiene DOS proyectos de la lista, que son prioridades distintas:**

| Dentro de `ANUNCIOS/` | Prioridad | Repo | Estado |
|---|---|---|---|
| `imports/anuncios_de_plataforma/` | **#4** Anuncios de Plataforma | `anuncios_de_plataforma` | checkout viejo: rama `feature/…` (sin guion bajo) y decenas de ficheros modificados sin commitear |
| `imagecarousel/` | **#5** Slider de Curso (presunto) | `anuncios_del_curso` ⟨por confirmar⟩ | repo git **sin remoto configurado**, una sola rama `master`, un commit `init` |
| `MANUAL INSTALACIÓN ANUNCIOS DE PLATAFORMA.pdf` | #4 | | |
| `MANUAL INSTALACIÓN ANUNCIOS DE CURSOS.pdf` | #5 | | |

Y ojo con las ramas del repo de #4, porque es donde se pierde una auditoría entera: en el remoto
conviven **`feature/slider-form_Carlos`** (`592c496`) y **`feature_test/slider-form_Carlos`**
(`a3c2603`), y **no son la misma**. La entrega auditada es `feature_test`. El checkout de
`ANUNCIOS/imports/` está en la otra.

⟨PENDIENTE: confirmar de dónde salió `ANUNCIOS/imagecarousel` y si corresponde a la prioridad #5.
Sin remoto configurado no se puede contrastar con nada del servidor.⟩

## Tabla completa

| # | Proyecto (lista) | Repo(s) | Carpeta local | Estado |
|---|---|---|---|---|
| 1 | Reportes de Integración | `adi` | `ADI/` | ✅ clonado en `ADI/adi` · auditado R1 |
| 2 | Reportes de Cursos | `analitica_cursos`, `reportes_de_curso` | — | ❌ **falta carpeta**; ambos repos existen |
| 3 | Reportes Administrativos | `analitica_notificaciones` | `ANALITICA NOTIFICACIONES/` | ⚠️ nombre engañoso: contiene el manual de Metabase, **ningún repo clonado** |
| 4 | Anuncios de Plataforma | `anuncios_de_plataforma` | `ANUNCIOS/` (mezclada) + **`ANUNCIOS DE PLATAFORMA/`** (nueva) | ✅ clon limpio en la carpeta nueva · auditado R2 |
| 5 | Slider de Curso | `anuncios_del_curso` | `ANUNCIOS/imagecarousel` | ⚠️ mezclada con #4 · repo sin remoto |
| 6 | Encuestas | `encuestas`, `encuestas_backend` | `ENCUESTAS/` | sin clonar |
| 7 | Portafolio del Aprendiz | `portafolio_del_aprendiz`, `…_2` | `PORTAFOLIO DEL APRENDIZ/` | sin clonar |
| 8 | Centro de Calificaciones | `centro_de_resultados`, `centro_de_actividades`, `centro_de_calificaciones_sincronizacion` | `CENTRO DE CALIFICACIONES/` | sin clonar · **3 repos** |
| 9 | Foros | `foros` | `FOROS/` | sin clonar |
| 10 | Antiplagio | `antiplagio` | `ANTIPLAGIO/` | perfil en el lab; `SRC_PATH` apunta a `/opt/…` |
| 11 | Móvil | `movil`, `movil_api` | `MOVIL/` | ⚠️ perfil en el lab pero **sin repos clonados**; solo el `.apk` |
| 12 | Chatbot | `chatbot` | `CHATBOT/` | sin clonar |
| 13 | CMS | `cms` | `CMS/` | sin clonar |
| 14 | Repositorio | `repositorio` | `REPOSITORIO/` | sin clonar |
| 15 | Gamificación | `gamificacion` | `GAMIFICACIÓN/` | sin clonar |
| 16 | Plugin XP Gamificación | `plugin_xp_gamificacion` | ⟨dentro de `GAMIFICACIÓN/`?⟩ | repo existe |
| 17 | H5P | `h5p` | — | ❌ **falta carpeta**; el repo existe |
| 18 | Proyectos IA | `ia_generador_de_texto` | `PROYECTO IA/` | sin clonar |
| 19 | Realidad Aumentada | `realidad_aumentada` | — | ❌ **falta carpeta**; el repo existe |
| 20 | Realidad Virtual | `realidad_virtual` | `REALIDAD VIRTUAL/` | sin clonar |
| 21 | Manos al Campo | `manos_al_campo` | `MANOS AL CAMPO/` | sin clonar |
| 22 | CultivaSENA | `cultivasena` | `CULTIVASENA/` | sin clonar |

### Carpetas sin fila en la lista de prioridad

| Carpeta | Qué es | Observación |
|---|---|---|
| `COSTOS WEB/` | proyecto auditado en la serie **R3–R10** | tiene perfil en el lab y **no está en la lista** |
| `ASISTENCIA/` | plugin de asistencia (`13_Asistencia_Plugin_Report_criteria.md`) | instalado en el Zajuna local (`local/asistencia`) |
| `AUTOINSCRIPCIÓN/` | plugin (`local/auto_inscripcion` en el Zajuna local) | |
| `ENVIO DE CORREOS/` | Mailer | ¿se solapa con el envío segmentado de #4? ⟨por confirmar⟩ |
| `IA DE PLAGAS Y ENFERMEDADES DEL CAFÉ/` | | |
| `LOGIN/` | | |
| `INFRALOCAL/` | infraestructura + histórico de informes | no es un proyecto auditable |
| `ZAJUNA NGINX/` | despliegue local de la plataforma | **es el entorno**, no un proyecto |
| `SECURITY-LAB/` | este laboratorio | |

## Qué propongo

**1. Separar la carpeta que mezcla dos prioridades** — es el único cambio que corrige un error
real y no solo cosmético:

```
ANUNCIOS/imports/anuncios_de_plataforma  →  ANUNCIOS DE PLATAFORMA/   (ya hecho: clon limpio)
ANUNCIOS/imagecarousel                   →  SLIDER DE CURSO/          (tras confirmar su origen)
```
Los dos PDF, cada uno con su proyecto.

**2. Convenio de nombres.** Hoy conviven tres criterios: nombre del proyecto en la lista
(`FOROS`), nombre del repo (`ANTIPLAGIO`), y nombre descriptivo que no coincide con ninguno
(`ANALITICA NOTIFICACIONES` para «Reportes Administrativos»). Propongo **el nombre de la lista**,
que es el que se usa al hablar y al asignar prioridad, con el repo dentro:

```
<NOMBRE DEL PROYECTO EN LA LISTA>/<repo1>/  <repo2>/  <manuales>
```
Con eso, `ANALITICA NOTIFICACIONES/` pasaría a `REPORTES ADMINISTRATIVOS/`.

**3. Añadir una columna a la lista de prioridad** con la carpeta local. Un cotejo hecho a mano
caduca; una columna no.

**4. Antes de mover nada**, actualizar `SRC_PATH` en `targets/antiplagio`, `targets/movil` y
`targets/costos_web`. Los tres apuntan a `/opt/MANUALES DE DESPLIEGUE WITH REPORT/…`, una ruta que
**ya no existe en esta máquina** — así que esos tres perfiles no resuelven su fuente hoy,
independientemente de lo que se renombre.
