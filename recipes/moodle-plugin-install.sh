#!/bin/bash
# Runs INSIDE the Moodle container, from the image's own post-init hook
# (/docker-entrypoint-init.d), i.e. after Moodle is fully installed and before Apache starts.
#
# Why a hook and not a `command:` override: the Bitnami entrypoint only runs the Moodle setup
# when the command is exactly its own run.sh. Overriding the command silently skips the whole
# installation — the container then starts with no config.php and no TLS certificates, and the
# failure looks like an Apache error, several layers away from its cause.
set -euo pipefail

PLUGIN_TYPE="${PLUGIN_TYPE:-local}"
DEST="/bitnami/moodle/${PLUGIN_TYPE}/${PLUGIN_DIR}"

echo "[lab] installing plugin ${PLUGIN_COMPONENT:-?} into ${DEST}"
mkdir -p "$(dirname "$DEST")"
# Copy, never mount: the audited source stays read-only and untouched, and Moodle gets a tree it
# is allowed to own.
cp -a /plugin-src "$DEST"

# This hook runs as root, but Apache does not. Anything the upgrade creates under moodledata
# would end up root-owned and unwritable by the web server, and Moodle answers every request
# with HTTP 500 "Invalid permissions detected when trying to create a directory" — a message
# that points at permissions but never at their cause. So: remember who owns the data directory,
# and give it back afterwards.
OWNER="$(stat -c '%u:%g' /bitnami/moodledata)"

# Let MOODLE create the plugin's tables through its own upgrade path. Hand-writing that schema
# would mean the audit measures a fiction instead of the real installation.
php /bitnami/moodle/admin/cli/upgrade.php --non-interactive --allow-unstable

chown -R "$OWNER" /bitnami/moodledata "$DEST"
echo "[lab] plugin installed, Moodle upgraded, ownership restored to $OWNER"
