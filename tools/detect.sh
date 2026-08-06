#!/usr/bin/env bash
# Sniff a source tree and PROPOSE target.env values + which recipes/linters apply.
# It never writes target.env: the controller confirms. Guessing wrong silently is how
# an audit ends up measuring the wrong thing.
set -uo pipefail

TARGET="${1:?usage: detect.sh <target>}"
ENVFILE="targets/$TARGET/target.env"
[ -f "$ENVFILE" ] || { echo "no $ENVFILE — run: make new TARGET=$TARGET"; exit 2; }

# Never `source` a target.env: values may contain spaces, and a profile is data, not code.
SRC=$(sed -n 's/^SRC_PATH=//p' "$ENVFILE" | tail -1 | sed 's/^"//; s/"$//')
[ -d "$SRC" ] || { echo "SRC_PATH not a directory: $SRC"; exit 2; }

echo "== detect: $TARGET =="
echo "source: $SRC"
echo

PRUNE=( -name node_modules -o -name vendor -o -name .git -o -name __pycache__ -o -name .venv )
scan() { find "$SRC" -type d \( "${PRUNE[@]}" \) -prune -o "$@" -print 2>/dev/null; }

LANGS=(); RECIPES=(); NOTES=()
add_note() { NOTES+=("$1"); }

# --- languages, by file census (a lockfile proves intent; a census proves reality) ---
count() { scan -type f -name "$1" | wc -l; }
N_PY=$(count '*.py'); N_PHP=$(count '*.php'); N_JS=$(count '*.js'); N_TS=$(count '*.ts'); N_GO=$(count '*.go')
echo "file census:  py=$N_PY  php=$N_PHP  js=$N_JS  ts=$N_TS  go=$N_GO"
[ "$N_PY"  -gt 0 ] && LANGS+=(py)
[ "$N_PHP" -gt 0 ] && LANGS+=(php)
{ [ "$N_JS" -gt 0 ] || [ "$N_TS" -gt 0 ]; } && LANGS+=(js)
[ "$N_GO"  -gt 0 ] && LANGS+=(go)

ADAPTER=none

# --- frameworks / how it boots ---
if [ -n "$(scan -type f -name artisan | head -1)" ]; then
  RECIPES+=(laravel-fpm)
  add_note "Laravel detected (artisan). recipes/laravel-fpm for load testing; laravel-artisan boots faster for functional runs."
  grep -rqls 'sanctum' "$SRC" --include='composer.json' 2>/dev/null && ADAPTER=sanctum
fi

if scan -type f \( -name requirements.txt -o -name pyproject.toml \) | head -1 | grep -q .; then
  if scan -type f \( -name requirements.txt -o -name pyproject.toml \) -exec grep -qil 'fastapi' {} \; -quit 2>/dev/null; then
    RECIPES+=(fastapi-uvicorn)
    add_note "FastAPI detected. HEALTH_PATH is usually /docs or an explicit /health route — confirm which."
  elif scan -type f -name requirements.txt -exec grep -qil 'django' {} \; -quit 2>/dev/null; then
    RECIPES+=(django)
  fi
fi

# Moodle plugin: version.php declaring a component. It CANNOT run standalone.
while IFS= read -r v; do
  [ -z "$v" ] && continue
  if grep -q 'plugin->component' "$v" 2>/dev/null; then
    COMP=$(grep -oP "plugin->component\s*=\s*'\K[^']+" "$v" | head -1)
    RECIPES+=(moodle-plugin); ADAPTER=moodle-session
    add_note "Moodle plugin '$COMP' — it has no entry point of its own; recipes/moodle-plugin brings up a Moodle to host it."
  fi
done < <(scan -type f -name version.php)

[ -n "$(scan -type f -name 'vite.config.*' | head -1)" ] && {
  RECIPES+=(vite-spa); add_note "Vite SPA detected — 'make build' is meaningful for this target."; }

# --- hybrid mobile (Ionic / Capacitor / Cordova) ---------------------------------------------
# Worth its own branch because it changes WHAT the audited object is. Everything else in this
# script describes something that runs on a server; a mobile project ships a signed bundle to
# other people's devices, and the bundle is not the repository — it carries compiled config,
# assets and third-party SDKs no source scan sees. A profile that does not declare
# MOBILE_ARTIFACT simply never audits the thing the project delivers.
CAPCFG=$(scan -type f -name 'capacitor.config.*' | head -1)
if [ -n "$CAPCFG" ] || [ -n "$(scan -type f -name 'ionic.config.json' | head -1)" ]; then
  RECIPES+=(capacitor-android)
  add_note "Hybrid mobile app (Ionic/Capacitor). Set MOBILE_ARTIFACT to the RELEASE bundle and run 'make mobile-scan'; add --config=/seclab-lib/semgrep/capacitor-android.yml to SEMGREP_CONFIG so the Android config is audited too."
  add_note "Its UI runs in a WebView, not a desktop browser: 'make budget' measures a browser this app never uses. The device dimension ('make device-e2e') is what covers real usage."

  # Red flags that are already findings — same treatment as a compose publishing on 0.0.0.0.
  # Comments are stripped first, and the wildcard must be an entry of its own ('*'), not the
  # `*.example.com` of a legitimate subdomain rule. Without both, the note fires on the comment
  # that explains why the wildcard was REMOVED — a warning that trains people to ignore warnings.
  if [ -n "$CAPCFG" ] && grep -qE "allowNavigation" "$CAPCFG" 2>/dev/null \
     && sed 's://.*::' "$CAPCFG" | grep -qE "(^|[[:space:],\[])['\"]\*['\"]" 2>/dev/null; then
    add_note "WARNING: capacitor allowNavigation contains '*' — the WebView, with its tokens and native bridge, may load any origin."
  fi
  NSC=$(scan -type f -name 'network_security_config.xml' | head -1)
  if [ -n "$NSC" ] && grep -q 'src="user"' "$NSC" 2>/dev/null; then
    add_note "WARNING: network_security_config trusts user-installed CAs. Inside <debug-overrides> that is fine; inside <domain-config> it ships to production and enables MITM."
  fi
  MAN=$(scan -type f -name 'AndroidManifest.xml' | head -1)
  [ -n "$MAN" ] && grep -q 'android:usesCleartextTraffic="true"' "$MAN" 2>/dev/null && \
    add_note "WARNING: manifest allows cleartext traffic app-wide."
  APK=$(scan -type f -name '*.apk' | head -1)
  [ -n "$APK" ] && echo "  candidate artifact: ${APK#"$SRC"/}"
fi
[ -n "$(scan -type f -name go.mod | head -1)" ] && RECIPES+=(go-binary)

# --- services the project already declares: reuse, do not reinvent ---
while IFS= read -r c; do
  [ -z "$c" ] && continue
  echo "  compose found: ${c#"$SRC"/}"
  grep -qE 'image:.*(postgres|mariadb|mysql)' "$c" 2>/dev/null && RECIPES+=(postgres)
  grep -qE 'image:.*kafka' "$c" 2>/dev/null && { RECIPES+=(kafka-zk)
    add_note "Kafka in the target's own compose — reuse that file as an overlay rather than rewriting it."; }
  grep -qE 'image:.*rabbitmq' "$c" 2>/dev/null && RECIPES+=(rabbitmq)
  grep -qE '^[[:space:]]*-[[:space:]]*"?0\.0\.0\.0:' "$c" 2>/dev/null && \
    add_note "WARNING: $(basename "$c") publishes on 0.0.0.0 — a finding in the target, and a risk while the lab holds its data."
  grep -qE 'ALLOW_ANONYMOUS_LOGIN|ALLOW_PLAINTEXT_LISTENER' "$c" 2>/dev/null && \
    add_note "WARNING: broker with anonymous/plaintext auth in $(basename "$c") — run 'make config-scan' and read the result."
done < <(scan -type f -name 'docker-compose*.y*ml')

# --- auth adapter fallback (only if nothing stronger matched) ---
if [ "$ADAPTER" = none ]; then
  grep -rqls 'OAuth2PasswordBearer\|Authorization: Bearer\|PyJWT\|jwt.encode' "$SRC" --include='*.py' 2>/dev/null && ADAPTER=jwt-bearer
fi

uniq_join() { printf '%s\n' "$@" | grep -v '^$' | awk '!seen[$0]++' | paste -sd, -; }
echo
echo "-- proposed target.env values (review, then paste) --"
echo "LANGS=$(uniq_join "${LANGS[@]:-}")"
echo "AUTH_ADAPTER=$ADAPTER"
# QODANA_IMAGE ya NO se propone aquí: se resuelve desde LANGS en tools/qodana-image.sh, en el
# momento de correr. Proponer un nombre a mano fue el origen del hueco — las imágenes que este
# script sugería (qodana-python, qodana-php) son las de pago, que se niegan a arrancar sin
# QODANA_TOKEN, así que el campo se quedaba vacío y la dimensión no corría en ningún proyecto.
echo "QODANA_IMAGE=            # déjalo vacío: el linter se resuelve desde LANGS al ejecutar."
echo "#   'make qodana TARGET=$TARGET' dirá qué imagen le toca y, si no le toca ninguna"
echo "#   gratuita para estos lenguajes, lo dirá como NO DISPONIBLE con su razón."
echo "#   QODANA_IMAGE=<imagen> fija una a mano; QODANA_IMAGE=none desactiva la dimensión."
echo "# recipes to compose in compose.runtime.yml: $(uniq_join "${RECIPES[@]:-none}")"
if [ "${#LANGS[@]}" -gt 1 ]; then
  echo "# NOTE: polyglot project. One Qodana image covers ONE language; the others are"
  echo "#       covered by SonarQube + semgrep. State that limit in the report."
fi
echo
echo "-- still REQUIRED from you (detection cannot infer these) --"
echo "  HEALTH_PATH      a path that returns 200 when the app is really up"
echo "  ROLE_A_/ROLE_B_  two accounts of DIFFERENT privilege, known password"
echo "                   (without these the authorization matrix cannot be tested at all)"
echo "  SOURCE_DIRS      which subdirs are yours vs vendored"
echo "  authz-matrix.json  which role may reach which path — the policy, which no tool knows"
[ "${#NOTES[@]}" -gt 0 ] && { echo; echo "-- notes --"; printf '  * %s\n' "${NOTES[@]}"; }
exit 0
