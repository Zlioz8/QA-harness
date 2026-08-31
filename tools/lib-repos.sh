# shellcheck shell=bash
# El ÚNICO descubridor de repositorios bajo SRC_PATH. Súrcelo; no lo copies.
#
# POR QUÉ EXISTE, primera mitad: la regla estaba escrita CUATRO veces, a mano, idéntica —
# tools/secrets.sh, tools/run-manifest.sh, tools/doctor.sh y tools/mobile-scan.sh. Es
# exactamente el caso de tools/lib-env.sh: cuatro copias de una decisión son cuatro
# oportunidades de divergir, y la divergencia aquí es invisible porque las cuatro siguen
# respondiendo, solo que sobre árboles distintos.
#
# POR QUÉ EXISTE, segunda mitad y la que importa más: hasta ahora SOLO secrets.sh descubría
# repos. Las demás dimensiones que miran código —semgrep, trivy fs, trivy config, syft,
# qodana— montaban ${SRC_PATH} ENTERO y analizaban lo que hubiera dentro. Y el contrato del
# perfil (targets/_template/target.env) dice que en un proyecto de varios repositorios
# SRC_PATH apunta al DIRECTORIO PADRE. Ese padre es una carpeta de escritorio de trabajo:
#
#   ANALITICA NOTIFICACIONES/
#     analitica_notificaciones/          <- el repositorio auditado
#     MANUAL DE INSTALACION ....docx     <- 941 KB de Word
#     MANUAL DE INSTALACION ....docx.pdf <- 825 KB
#     zv5-menu.png                       <- una captura de pantalla
#     .playwright-mcp/                   <- logs de consola y red de una sesión MCP
#                                           de OTRO proyecto (slider_form)
#
# Medido sobre ese directorio: sin este módulo, `make deps` y `make semgrep` habrían escaneado
# los cinco, y sus hallazgos habrían salido en el informe como cobertura de
# analitica_notificaciones. Eso es la definición del modo de fallo que este laboratorio existe
# para no cometer: medir otra cosa con el nombre de este proyecto.
#
# LA REGLA, y es una sola para que no pueda divergir:
#   - si SRC_PATH es él mismo un repositorio git -> el árbol a analizar es SRC_PATH ("." )
#   - si no -> son sus hijos de UN nivel que tengan .git
#   - si no hay ninguno -> vacío, y cada consumidor decide qué significa eso PARA ÉL
#     (secrets.sh escanea el árbol de trabajo; run-dimension.sh cae al comportamiento de
#     siempre). Nunca se inventa un repositorio.
#
# UN NIVEL, no `find`: un `find -name .git` bajaría a node_modules y a vendor, donde hay
# repositorios de terceros. El contrato dice "el padre, o sus hijos"; eso es lo que se busca.

# discover_repos <src_path>
#   Imprime una ruta RELATIVA por línea: "." o el nombre de cada subdirectorio-repositorio.
#   Relativas porque los contenedores ven el árbol montado en /repo, /src o /data/project, y
#   la ruta de dentro no es la de fuera.
discover_repos() {
  local src="${1:-}"
  [ -n "$src" ] && [ -d "$src" ] || return 0
  if [ -d "$src/.git" ]; then
    echo "."
    return 0
  fi
  local d
  for d in "$src"/*/; do
    [ -d "$d.git" ] && basename "$d"
  done
}

# src_roots <src_path>
#   Imprime una ruta ABSOLUTA por línea: el árbol que cada pase debe montar.
#   Es lo que consume tools/run-dimension.sh para las dimensiones `per_repo`.
#   Si no hay ningún repositorio, imprime el propio SRC_PATH: una dimensión que no encuentra
#   git tiene que seguir analizando bytes reales — un informe vacío porque no se escaneó nada
#   es indistinguible de uno limpio, y esa confusión es precisamente lo prohibido.
src_roots() {
  local src="${1:-}" rel any=0
  [ -n "$src" ] && [ -d "$src" ] || return 0
  while IFS= read -r rel; do
    [ -z "$rel" ] && continue
    any=1
    if [ "$rel" = "." ]; then printf '%s\n' "$src"; else printf '%s\n' "$src/$rel"; fi
  done < <(discover_repos "$src")
  [ "$any" -eq 0 ] && printf '%s\n' "$src"
  return 0
}

# non_repo_entries <src_path>
#   Lo que queda FUERA del análisis: las entradas de primer nivel de SRC_PATH que no son
#   ninguno de los repositorios descubiertos.
#
#   Existe porque acotar la entrada en silencio es la otra mitad del mismo defecto. Antes se
#   analizaba de más sin decirlo; analizar de menos sin decirlo no es mejor. tools/run-manifest.sh
#   lo escribe en RUN.md para que la cobertura declarada sea la real y se pueda discutir.
#   Vacío cuando SRC_PATH es él mismo el repositorio: ahí no se excluye nada.
non_repo_entries() {
  local src="${1:-}" e base
  [ -n "$src" ] && [ -d "$src" ] || return 0
  [ -d "$src/.git" ] && return 0        # el propio SRC_PATH es el repo: no sobra nada
  for e in "$src"/* "$src"/.[!.]*; do
    [ -e "$e" ] || continue
    base="$(basename "$e")"
    [ -d "$e/.git" ] && continue        # es uno de los repositorios descubiertos
    printf '%s\n' "$base"
  done
}
