# configs/

Sitio de la llave de despliegue que usa `make clone` (`deploy_key` y `deploy_key.pub`): una llave
DEDICADA al laboratorio, nunca la `~/.ssh` del operador (hallazgo L2 del hardening, en
`docs/historial/INFORME_HARDENING_SECURITY_LAB.md`). `.gitignore` la excluye y `docker-compose.yml`
la monta desde aquí salvo que `DEPLOY_KEY` indique otra ruta.

Aquí no va configuración de herramientas: cada una se configura en `lib/dimensions.yml` (núcleo) o
en `targets/<perfil>/` (por proyecto). Un `trivy.yaml` vivió aquí sin que ningún servicio lo
montara; se retiró el 2026-09-24.
