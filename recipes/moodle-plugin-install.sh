#!/bin/bash
# Runs INSIDE the Moodle container, from the image's own post-init hook
# (/docker-entrypoint-init.d), i.e. after Moodle is fully installed and before Apache starts.
#
# Why a hook and not a `command:` override: the Bitnami entrypoint only runs the Moodle setup
# when the command is exactly its own run.sh. Overriding the command silently skips the whole
# installation — the container then starts with no config.php and no TLS certificates, and the
# failure looks like an Apache error, several layers away from its cause.
set -euo pipefail

# Where a plugin goes is not a question for the operator: `$plugin->component` in version.php
# already says it. `local_slider_form` means local/slider_form, `block_foo` means blocks/foo.
# Deriving it removes PLUGIN_TYPE/PLUGIN_DIR as things to get wrong, and — the reason this
# changed — a repository holding SEVERAL plugins installs all of them, which is the normal shape
# of a Moodle component repo. One-plugin profiles behave exactly as before.
#
# Moodle's directory for a plugin type is not always the type name: block_ lives in blocks/,
# and the -one-off plurals below are the ones a component repo actually ships.
plugin_dir_for() {
  case "$1" in
    block)  echo "blocks"  ;;
    mod)    echo "mod"     ;;
    theme)  echo "theme"   ;;
    qtype)  echo "question/type" ;;
    report) echo "report"  ;;
    *)      echo "$1"      ;;   # local, auth, enrol, tool, filter … match their own name
  esac
}

INSTALLED=0
# maxdepth 2: the mount is either the plugin itself or a directory of plugins. Deeper would
# start matching version.php files vendored inside a plugin's own subtree.
while IFS= read -r vfile; do
  comp=$(sed -n "s/.*plugin->component[[:space:]]*=[[:space:]]*'\([^']*\)'.*/\1/p" "$vfile" | head -1)
  src=$(dirname "$vfile")
  if [ -z "$comp" ]; then
    echo "[lab] skipping $src — version.php declares no component"
    continue
  fi
  type="${comp%%_*}"
  name="${comp#*_}"
  DEST="/bitnami/moodle/$(plugin_dir_for "$type")/${name}"
  echo "[lab] installing ${comp} -> ${DEST}"
  mkdir -p "$(dirname "$DEST")"
  # Copy, never mount: the audited source stays read-only and untouched, and Moodle gets a tree
  # it is allowed to own.
  rm -rf "$DEST"
  cp -a "$src" "$DEST"
  INSTALLED=$((INSTALLED + 1))
  DESTS="${DESTS:-} $DEST"
done < <(find /plugin-src -maxdepth 2 -name version.php -type f | sort)

if [ "$INSTALLED" -eq 0 ]; then
  echo "[lab] FATAL: no version.php with a component under /plugin-src." >&2
  echo "[lab] PLUGIN_SUBDIR points at the wrong directory; nothing was installed, and a" >&2
  echo "[lab] Moodle without the plugin would be audited as if it had it." >&2
  exit 1
fi
echo "[lab] $INSTALLED plugin(s) staged"

# This hook runs as root, but Apache does not. Anything the upgrade creates under moodledata
# would end up root-owned and unwritable by the web server, and Moodle answers every request
# with HTTP 500 "Invalid permissions detected when trying to create a directory" — a message
# that points at permissions but never at their cause. So: remember who owns the data directory,
# and give it back afterwards.
OWNER="$(stat -c '%u:%g' /bitnami/moodledata)"

# Let MOODLE create the plugin's tables through its own upgrade path. Hand-writing that schema
# would mean the audit measures a fiction instead of the real installation.
php /bitnami/moodle/admin/cli/upgrade.php --non-interactive --allow-unstable

# shellcheck disable=SC2086  — DESTS is a deliberately word-split list of destinations
chown -R "$OWNER" /bitnami/moodledata $DESTS
echo "[lab] $INSTALLED plugin(s) installed, Moodle upgraded, ownership restored to $OWNER"
