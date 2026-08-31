Agrupado por quién lo remedia, en orden de impacto dentro de cada grupo:

**Backend (dueño del código de la API y del SSO)**
1. Rotar la clave HS256 y sacar `.env` del control de versiones (§3.1). Es la raíz de todo el
   bloque de sesión y no depende de nadie más.
2. Subir `python-jose` a 3.4.0+ y `python-multipart` a 0.0.30+ (§3.2, §3.4). Cambios de una línea
   en `requirements.txt`.
3. Decidir y arreglar el router `admin` + el catch-all para que `/api/*` desconocido dé 404 (§3.5).
4. Revisar `redirect.php` (aleatoriedad, §3.3), mover el token del SSO fuera de la URL (§3.6) y
   acotar el *fail-open* de la revalidación (§3.9).

**DevOps / Infra (dueño del proxy y del despliegue)**
5. Añadir las cabeceras de seguridad en nginx (§3.7) — barato y de alto retorno.
6. Crear el rol de solo lectura `reportes_ro` y fijar `MOODLE_DB_NAME` verificado (§3.10).

**Líder Técnico (proceso)**
7. Publicar `.env.example` y montar un pipeline mínimo con escaneo de secretos que bloquee el
   build si `.env` reaparece (§3.8). Cierra el hueco que originó §3.1.

**Insumo pendiente para completar la próxima ronda**
8. Una cuenta de **bajo privilegio con acceso a reportes** (rol `teacher`/`student` según el plugin)
   para poder medir la matriz de autorización entre usuarios, hoy NO DISPONIBLE.
