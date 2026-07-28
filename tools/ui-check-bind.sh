#!/usr/bin/env bash
# Verify from the HOST that the UI is published on loopback only.
#
# This is the lab's security model in one check. The UI container holds /var/run/docker.sock, so
# whatever reaches its port can start arbitrary containers — root on this machine. Confinement is
# not something the Python process can enforce (inside its own network namespace it must bind
# 0.0.0.0); it is a property of the published port mapping, observable only from out here.
#
# On failure it stops the UI rather than warning about it. A warning printed into a terminal
# nobody is reading is how the lab's own finding L1 happened: services published on 0.0.0.0 while
# holding real data.
set -uo pipefail

# Found by compose label rather than by `docker compose ps`: this script must work standalone,
# and a compose invocation here would need the same placeholder variables the Makefile sets, or
# it fails to parse the file and reports "not running" for a container that is running fine.
CID=$(docker ps -q --filter "label=com.docker.compose.service=ui" | head -1)
if [ -z "$CID" ]; then
  echo "  la interfaz no está corriendo"
  exit 1
fi

BINDS=$(docker inspect --format \
  '{{range $p, $conf := .NetworkSettings.Ports}}{{range $conf}}{{$p}} -> {{.HostIp}}:{{.HostPort}}
{{end}}{{end}}' "$CID" 2>/dev/null)

BAD=$(echo "$BINDS" | grep -vE '^\s*$' | grep -vE '\-> (127\.0\.0\.1|::1):' || true)

if [ -n "$BAD" ]; then
  echo
  echo "  PELIGRO: la interfaz está publicada fuera de loopback:"
  echo "$BAD" | sed 's/^/      /'
  echo
  echo "  Tiene el socket de Docker: cualquiera que alcance ese puerto ejecuta contenedores"
  echo "  arbitrarios en este host. Se apaga ahora."
  echo
  docker compose -f docker-compose.yml --profile ui down >/dev/null 2>&1
  exit 1
fi

echo "$BINDS" | grep -E '\->' | sed 's/^/  publicado en /'
exit 0
