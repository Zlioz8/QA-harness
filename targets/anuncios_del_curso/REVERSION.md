# Reversión — despliegue de `mod_imagecarousel` en el Zajuna bare metal

> **Este documento se escribió ANTES de instalar nada.** Existe porque el despliegue de este
> proyecto no ocurre en un contenedor efímero: escribe en `/var/www/zajuna/mod/` y ejecuta un
> upgrade contra la base `moodle` de PostgreSQL, que es **la misma** que leen otros tres
> proyectos ya auditados (#2 reportes_de_cursos, #3 analitica_notificaciones, #6 encuestas).
>
> Es el despliegue más invasivo de los seis y el único cuyo fallo puede tumbar a los otros. Sin
> una vuelta atrás escrita y verificada antes del primer comando, deja de ser una medición
> reproducible y pasa a ser un cambio irreversible.

## Estado ANTES del despliegue (capturado el 2026-08-25, medido, no supuesto)

| Hecho | Valor |
|---|---|
| Moodle | `4.3.3+ (Build: 20240308)`, `dirroot=/var/www/zajuna`, `dataroot=/var/www/zajunadata` |
| `wwwroot` | `https://nginx.zajuna.com/zajuna` |
| Servidor web | **nginx 1.24.0 (Ubuntu)** — `apache2` instalado: **0 paquetes** |
| PHP | **8.1.34** vía `php8.1-fpm`, socket `/run/php/php8.1-fpm-zajuna.sock`, usuario `www-data` |
| Base / usuario / prefijo | `moodle` / `moodle` / `mdl_` · esquemas `public` + `midb` |
| `mod/imagecarousel` en el árbol | **no existe** (`mod/` tiene 30 entradas, ninguna es esta) |
| `mdl_modules` | **26 filas**, ninguna `imagecarousel` |
| `mdl_config_plugins` | **2371 filas**, ninguna con `plugin like '%carousel%'` |
| `to_regclass('public.mdl_imagecarousel')` | **vacío** (la tabla no existe) |
| `to_regclass('public.mdl_imagecarousel_images')` | **vacío** |
| `mdl_upgrade_log` | **1488 filas**, ninguna entrada de `mod_imagecarousel` |

**Conclusión que debe constar explícita, no implícita:** se audita una **instalación limpia**.
No hay ninguna instancia heredada de la QA manual de mayo de 2026 sobre la que estemos midiendo.
La decisión «auditar sobre lo que hubiera» / «desinstalar limpio primero» no se plantea porque no
hay nada que desinstalar.

## Artefactos del respaldo

Directorio: `/home/zlioz/MANUALES DE DESPLIEGUE WITH REPORT/SLIDER DE CURSO/_respaldo_pre_imagecarousel/`

| Fichero | Qué es | Verificación hecha |
|---|---|---|
| `moodle_pre_imagecarousel.dump` | `pg_dump -Fc` de la base `moodle` completa (301.112.117 bytes) | `pg_restore -l` → **6828** entradas, **554** `TABLE DATA public mdl_*`, **83** entradas del esquema `midb` |
| `estado_previo_mdl_modules.tsv` | las 26 filas de `mdl_modules` | 28 líneas (cabecera + 26 + total) |
| `estado_previo_config_plugins.tsv` | volcado de `mdl_config_plugins` | 2676 líneas |
| `estado_previo_mod_dir.txt` | `ls -la /var/www/zajuna/mod/` | 33 líneas |
| `checksums.txt` | `sha256sum` de todo lo anterior | — |

> **Nota de método, heredada del #4 y respetada aquí.** En aquella ronda un `pg_dump` devolvió
> `rc=0` y **no escribió nada**: el usuario `postgres` no puede escribir bajo `/home/zlioz`, y el
> `0` venía del `tail` del pipeline, no del `pg_dump`. Por eso aquí se volcó a `/tmp`, se movió, y
> se comprobó **el fichero** —tamaño y contenido con `pg_restore -l`— en vez del código de salida.
> Una operación que *parece* haber ocurrido es el modo de fallo que este laboratorio persigue.

## Por qué NO hay tar del árbol

En el #4 se guardó `zajuna_local_pre.tar.gz` porque `local/` ya contenía cuatro plugins que el
despliegue podía pisar. Aquí no aplica: `mod/imagecarousel` **no existe**, así que el despliegue
sólo puede **crear** un directorio nuevo, nunca sobrescribir uno. Revertir el árbol es borrar lo
que se creó. Se deja dicho en vez de guardar 400 MB de `mod/` del núcleo por simetría.

## Procedimiento de vuelta atrás

Ejecutar en este orden. **Por la vía de Moodle, nunca `rm -rf` a secas**: borrar el directorio
deja las filas de `mdl_modules`, `mdl_config_plugins` y las dos tablas en la base, y entonces
Moodle arranca pidiendo un upgrade de un plugin cuyo código ya no está — que es una plataforma
rota para los otros tres proyectos, no una reversión.

```bash
BK="/home/zlioz/MANUALES DE DESPLIEGUE WITH REPORT/SLIDER DE CURSO/_respaldo_pre_imagecarousel"
MOODLE_ROOT=/var/www/zajuna

# 0. Comprobar que el respaldo sigue siendo el que se selló.
cd "$BK" && sha256sum -c checksums.txt

# 1. Simulacro primero. uninstall_plugins.php corre en dry-run salvo que se pase --run
#    (DEPLOY.md §22.2). Se mira lo que dice ANTES de dejarle tocar nada.
sudo -u www-data php $MOODLE_ROOT/admin/cli/uninstall_plugins.php \
     --plugins=mod_imagecarousel

# 2. Desinstalar de verdad: quita las filas de mdl_modules y mdl_config_plugins,
#    elimina las tablas mdl_imagecarousel* y borra los ficheros del plugin del área de archivos.
sudo -u www-data php $MOODLE_ROOT/admin/cli/uninstall_plugins.php \
     --plugins=mod_imagecarousel --run

# 3. Retirar el código (Moodle deja el directorio; borrarlo AHORA sí es correcto,
#    porque la base ya no lo referencia).
sudo rm -rf $MOODLE_ROOT/mod/imagecarousel

# 4. Purgar cachés: sin esto Moodle sigue sirviendo el mapa de plugins cacheado.
sudo -u www-data php $MOODLE_ROOT/admin/cli/purge_caches.php

# 5. Verificar que se volvió al estado de la tabla de arriba.
psql -h localhost -U moodle -d moodle -tAc \
  "select count(*) from mdl_modules;"                                    # esperado: 26
psql -h localhost -U moodle -d moodle -tAc \
  "select to_regclass('public.mdl_imagecarousel');"                      # esperado: vacío
psql -h localhost -U moodle -d moodle -tAc \
  "select count(*) from mdl_config_plugins where plugin like '%carousel%';"  # esperado: 0
```

### Última red, sólo si el paso 2 deja la base inconsistente

```bash
# Restaura la base ENTERA al estado del dump. Destruye cualquier cambio hecho por
# CUALQUIER proyecto desde las 08:26 del 2026-08-25 — avisar a #2, #3 y #6 antes.
sudo -u postgres pg_restore --clean --if-exists --no-owner -d moodle \
     "$BK/moodle_pre_imagecarousel.dump"
```

> El dump es la **última** red, no la primera. Restaurarlo revierte también el trabajo de los
> otros tres proyectos que comparten la base, y por eso el camino normal es el de Moodle.

## Lo que este despliegue NO va a tocar

- **`zajuna.conf` / nginx.** Verificado antes de instalar: el core ya sirve el árbol entero con
  `location /zajuna` y `location ~ ^/zajuna(/[^?]*\.php)` hacia `php8.1-fpm-zajuna.sock`. Un
  plugin `mod` cuelga de ese árbol y **no necesita ninguna `location` nueva**. Si hubiera que
  añadir algo, se añade con copia previa y `nginx -t` — nunca se reescribe el fichero (el script
  de #2 lo reescribía entero y habría tumbado el CMS de `/`).
- **`pg_hba.conf`.** El plugin lee su propia base por la conexión de Moodle; no hace falta rol de
  sólo lectura ni línea nueva para la red Docker.
- **Puertos.** Este proyecto no publica ninguno. `PUERTOS.md` no cambia.
- **Los otros despliegues.** Ningún `make down` de #2, #3 ni #6.

## Estado final decidido

El plugin **queda instalado** tras el informe, igual que `local_slider`/`local_slider_form` (#4),
`local_reporteszajuna` (#3) y `block_zajuna_early_alert` (#2), para que una R2 no exija volver a
montar el despliegue (METODOLOGÍA §6: lo caro no se repite). Este procedimiento queda escrito y
verificado por si se decide lo contrario.
