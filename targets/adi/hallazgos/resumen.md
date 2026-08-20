**ADI no está en condiciones de considerarse desplegable ni expuesto tal como está hoy.** No por
la calidad funcional —la aplicación arranca, autentica y sirve sus pantallas— sino por tres
bloques concretos, y esta es la primera ronda, así que ninguno arrastra historial.

**1. El entorno de validación está abierto.** El directorio `.git` completo se descarga por HTTP
(§3.1), un archivo de respaldo sirve un token de SonarQube vivo en claro (§3.2), y la cuenta de
máximo privilegio usa `superadmin` / `password` (§3.3) sobre un host alcanzable desde internet.
Los tres se verificaron en vivo, no se dedujeron. Los dos primeros ya estaban en la auditoría
manual del 30 de julio: llevan tres semanas sin corregirse.

**2. El repositorio no reconstruye el sistema.** `composer.json` y `composer.lock` están en
`.gitignore` (§3.4), dos migraciones no aplican sobre una base limpia (§3.6) y una tabla que el
código usa no la crea ninguna migración (§3.7). Se comprobó desplegando desde cero: la aplicación
solo arranca aportando archivos que hay que copiar de otra máquina. Un servidor nuevo, o una
recuperación ante desastre, arranca roto.

**3. Faltan controles transversales.** Solo 3 de 9 controladores que mutan estado registran
protección CSRF (§3.9) — y entre los desprotegidos está el que crea cronjobs ejecutados por SSH
en otro servidor. No hay cabeceras de seguridad (§3.11), el listado de directorios está activo
(§3.10) y no existe integración continua (§3.13): nada verifica este proyecto salvo esta
auditoría.

**Sobre las cifras de carga.** La prueba con k6 arroja un 19,15% de error agregado, y leído sin
desglosar diría que el sistema es inestable. No lo es: el p95 es de 259 ms sobre un presupuesto
de 2000 ms, y cuatro de cinco pantallas responden 90 de 90. Todo el error procede de una única
ruta caída al 100% (§3.8).

**Y una limitación de esta ronda que conviene tener presente:** la dimensión de CVE de
dependencias informa 0 hallazgos, pero eso es consecuencia de §3.4 —no hay manifiesto que
analizar—, no evidencia de un árbol de dependencias limpio. **Esa cifra no es autoritativa.**
