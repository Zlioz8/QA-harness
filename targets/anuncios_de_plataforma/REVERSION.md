# Reversión — despliegue de `local_slider` + `local_slider_form` en el Zajuna bare metal

> Este documento existe porque el despliegue de esta ronda **no** ocurre en un contenedor
> efímero: escribe en `/var/www/zajuna/local/` y en la base `moodle` de PostgreSQL, que es la
> réplica de producción montada el 18-ago-2026. Sin una vuelta atrás escrita y verificada, el
> despliegue deja de ser una medición reproducible y pasa a ser un cambio irreversible.

## Estado ANTES del despliegue (2026-08-19, capturado por QA)

| Hecho | Valor |
|---|---|
| Moodle | `4.3.3+ (Build: 20240308)`, `dirroot=/var/www/zajuna`, `dataroot=/var/www/zajunadata` |
| `wwwroot` | `https://nginx.zajuna.com/zajuna` |
| Base / usuario / prefijo | `moodle` / `moodle` / `mdl_` |
| Plugins en `local/` | `antiplagiarsena`, `asistencia`, `auto_inscripcion`, `o365` (+ `auto_inscripcion.tar`, `readme.txt`, `upgrade.txt`) |
| `mdl_local_slider` | **no existe** (`to_regclass` → vacío) |
| Filas en `mdl_config_plugins` para `local_slider%` | **ninguna** |
| Esquema `midb` | **existe ya**, con `envios1` (127 filas) y `envios_log` (918 filas), propiedad de `postgres` |
| Tipo `midb.env_estado` | enum: `pendiente, en_proceso, enviado, fallo, cancelado` |
| Privilegios de `moodle` sobre `midb` | `USAGE=f`, `CREATE=f` — **ninguno** |

## Artefactos del respaldo

Directorio: `/home/zlioz/MANUALES DE DESPLIEGUE WITH REPORT/ANUNCIOS DE PLATAFORMA/_respaldo_pre_slider_form/`

| Fichero | Qué es | Verificación hecha |
|---|---|---|
| `moodle_pre_slider_form.dump` | `pg_dump -Fc` de la base `moodle` completa (298 MB) | `pg_restore -l` → **6587** entradas, **543** `TABLE DATA public mdl_*`, esquema `midb` + `env_estado` + `envios1` + `envios_log` presentes |
| `zajuna_local_pre.tar.gz` | `/var/www/zajuna/local/` completo (5,3 MB) | `tar -tzf` lista los 4 plugins previos |
| `estado_previo_config_plugins.tsv` | Volcado de `mdl_config_plugins` (2613 filas) | — |
| `estado_previo_midb.txt` | Tablas de `midb` antes de tocar nada | — |
| `estado_previo_local_dir.txt` | `ls /var/www/zajuna/local/` | — |
| `checksums.txt` | `sha256sum` de todo lo anterior | — |

> **Nota de método.** El primer intento de `pg_dump` devolvió `rc=0` y **no escribió nada**: el
> usuario `postgres` no puede escribir bajo `/home/zlioz`, y el `0` venía del `tail` del
> pipeline, no del `pg_dump`. Se detectó al comprobar el fichero, no al mirar el código de
> salida. Queda anotado porque es el mismo modo de fallo que el laboratorio persigue: una
> operación que *parece* haber ocurrido.

## Procedimiento de vuelta atrás

Ejecutar en este orden. Cada paso es independiente del anterior.

```bash
BK="/home/zlioz/MANUALES DE DESPLIEGUE WITH REPORT/ANUNCIOS DE PLATAFORMA/_respaldo_pre_slider_form"

# 0. Comprobar que el respaldo sigue siendo el que se selló.
cd "$BK" && sha256sum -c checksums.txt

# 1. Quitar los plugins del árbol de Moodle.
sudo rm -rf /var/www/zajuna/local/slider_form /var/www/zajuna/local/slider

# 2. Restaurar el árbol local/ tal cual estaba.
sudo tar -xzf "$BK/zajuna_local_pre.tar.gz" -C /var/www/zajuna
sudo chown -R www-data:www-data /var/www/zajuna/local

# 3. Restaurar la base. --clean --if-exists deja la base en el estado del dump,
#    incluidas las tablas midb.* que el despliegue haya creado.
sudo -u postgres pg_restore --clean --if-exists --no-owner -d moodle \
     "$BK/moodle_pre_slider_form.dump"

# 4. Purgar cachés de Moodle (la MUC guarda el registro de plugins).
sudo -u www-data php /var/www/zajuna/admin/cli/purge_caches.php
```

### Vuelta atrás PARCIAL (solo el esquema, sin restaurar 298 MB)

Si lo único que hay que deshacer son las tablas que crean las migraciones del plugin:

```sql
-- NO tocar envios1 ni envios_log: son de producción y PREEXISTEN al despliegue.
DROP TABLE IF EXISTS midb.saved_filters, midb.envios2, midb.centros, midb.regionales CASCADE;
DELETE FROM mdl_config_plugins WHERE plugin IN ('local_slider','local_slider_form');
DELETE FROM mdl_role_capabilities WHERE capability LIKE 'local/slider_form:%';
DROP TABLE IF EXISTS mdl_local_slider;
```

> ⚠️ **`midb.envios1` y `midb.envios_log` no se tocan en ningún caso.** Preexisten al
> despliegue, tienen datos reales (127 / 918 filas) y no pertenecen a este plugin.

## Verificación de que la reversión funcionó

```bash
sudo -u postgres psql -d moodle -Atc "SELECT to_regclass('public.mdl_local_slider');"   # → vacío
sudo -u postgres psql -d moodle -Atc \
  "SELECT count(*) FROM mdl_config_plugins WHERE plugin LIKE 'local_slider%';"          # → 0
sudo -u postgres psql -d moodle -Atc \
  "SELECT table_name FROM information_schema.tables WHERE table_schema='midb' ORDER BY 1;"
# → envios1, envios_log   (y nada más)
ls /var/www/zajuna/local/    # → antiplagiarsena asistencia auto_inscripcion o365 (+ los 3 sueltos)
curl -sk -o /dev/null -w '%{http_code}\n' https://nginx.zajuna.com/zajuna/login/index.php  # → 200
```

## Añadido el 19-ago-2026: cuentas de QA en el Zajuna local

Creadas con la CLI de Moodle (`user_create_user`), con roles preexistentes:

| Usuario | id | Rol asignado (contexto sistema) |
|---|---|---|
| `qa_slider_alto` | 38907 | `manager` (id 1) |
| `qa_slider_bajo` | 38908 | `student` (id 5) |

Para deshacerlo:

```sql
DELETE FROM mdl_role_assignments WHERE userid IN (38907, 38908);
UPDATE mdl_user SET deleted = 1 WHERE id IN (38907, 38908);
-- y si se llegaron a conceder las capabilities al rol manager:
DELETE FROM mdl_role_capabilities
 WHERE capability LIKE 'local/slider_form:%' AND roleid = 1;
```
Después: `sudo -u www-data php /var/www/zajuna/admin/cli/purge_caches.php`
