#!/usr/bin/env bash
# ¿La documentación sigue diciendo la verdad sobre lo que hace el laboratorio?
#
# La tabla de dimensiones de README.md y MANUAL_USO_QA.md era la SÉPTIMA copia de la lista que
# vivía en lib/dimensions.yml. Y estaba desactualizada exactamente igual que las otras seis:
# anunciaba `trufflehog.txt` como artefacto cuando el gate lee `trufflehog.sarif`, y no mencionaba
# la dimensión del artefacto móvil ni la del dispositivo.
#
# Una tabla en un documento envejece MÁS rápido que el código, porque nada falla cuando miente.
# Esto es lo que la hace fallar.
#
# Uso: tools/doc-check.sh          (normalmente: make doc-check)
set -uo pipefail

BEG="<!-- dimensiones:inicio -->"
END="<!-- dimensiones:fin -->"
DOCS=(README.md MANUAL_USO_QA.md)
FAIL=0

ok()  { printf '  \033[32mok\033[0m    %s\n' "$1"; }
bad() { printf '  \033[31mFAIL\033[0m  %s\n' "$1"; FAIL=1; }

echo "== doc-check =="

GEN=$(tools/dimensions.py --markdown) || { echo "no se pudo leer el registro"; exit 1; }

for doc in "${DOCS[@]}"; do
  if ! grep -qF "$BEG" "$doc"; then
    bad "$doc no tiene el bloque generado ($BEG)"
    continue
  fi
  # Extraer solo las filas de la tabla dentro del bloque: el texto de alrededor (la nota) puede
  # cambiar sin que eso sea una divergencia con el registro.
  have=$(awk -v b="$BEG" -v e="$END" '$0==b{f=1;next} $0==e{f=0} f' "$doc" | grep '^|' || true)
  if [ "$have" = "$GEN" ]; then
    ok "$doc: la tabla coincide con el registro"
  else
    bad "$doc: la tabla DIVERGE de lib/dimensions.yml"
    echo "        Regenera con:  tools/dimensions.py --markdown"
    diff <(echo "$GEN") <(echo "$have") | sed 's/^/          /' | head -12
  fi
done

# Segundo control: que la documentación no siga nombrando artefactos que ya no existen. Cada uno
# de estos fue real — `trufflehog.txt` era lo que la tabla anunciaba mientras el gate leía otra
# cosa, y `zap-report.json` fue la causa de que la pantalla de triaje se comiera ZAP entero.
echo
for doc in "${DOCS[@]}"; do
  stale=$(grep -noE 'trufflehog\.txt|zap/zap-report\.json' "$doc" || true)
  if [ -n "$stale" ]; then
    bad "$doc nombra artefactos obsoletos:"
    echo "$stale" | sed 's/^/          línea /'
  else
    ok "$doc: sin artefactos obsoletos"
  fi
done

echo
[ "$FAIL" -eq 0 ] && echo "documentación consistente con el registro" \
                  || { echo "documentación DESACTUALIZADA"; exit 1; }
