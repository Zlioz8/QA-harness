#!/bin/bash
# Copia las DOS apps a un DocumentRoot escribible (el /src va read-only), instala dependencias y
# escribe el .env de cada una. El laboratorio observa; no modifica el árbol auditado.
set -euo pipefail
declare -A MAP=( [centro_de_actividades]=lmsActividad [centro_de_resultados]=lms-califica )
for repo in "${!MAP[@]}"; do
  dest="/var/www/html/${MAP[$repo]}"
  echo "runtime: $repo -> $dest"
  mkdir -p "$dest"
  cp -a "/src/$repo/." "$dest/"
  if [ -f "$dest/composer.json" ]; then
    ( cd "$dest" && composer install --no-interaction --no-progress --prefer-dist 2>&1 | tail -3 ) || echo "runtime: AVISO composer install falló en $repo"
  fi
  # .env aportado por el perfil (sandbox), si existe; si no, desde .env.example
  if [ -f "/deps/${MAP[$repo]}.env" ]; then cp "/deps/${MAP[$repo]}.env" "$dest/.env"; echo "runtime: .env del perfil para ${MAP[$repo]}";
  elif [ -f "$dest/.env.example" ]; then cp "$dest/.env.example" "$dest/.env"; echo "runtime: .env desde .env.example (plantilla)"; fi
  chown -R www-data:www-data "$dest"
done
echo "runtime: DocumentRoot listo:"; ls -la /var/www/html/
exec apache2-foreground
