#!/usr/bin/env bash
# Antes de cada paso: cuánto ocupan y cuántas filas tienen las tablas de la base de la API.
# La diferencia con hook-despues.sh es lo que ESCRIBE la API por cada petición (crecimiento de
# disco por uso), que no sale de ningún documento.
DIR="${1:?}"
"$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/tablas.sh" > "$DIR/tablas-antes.csv" 2>"$DIR/tablas-antes.err"
