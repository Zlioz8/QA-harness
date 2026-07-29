#!/usr/bin/env bash
# Create the two unequal accounts the authorization matrix needs, through Moodle's own APIs.
#
# Why not INSERT rows: a Moodle user carries password hashing, an auth plugin, a context and
# role assignments. A hand-inserted row logs in badly or not at all, and a failed authorization
# test then means "the seed was wrong" rather than "the application is safe" — the worst possible
# outcome for an audit, because it reads as a pass.
#
# What makes THIS profile's seed different from a generic one: db/access.php declares
#
#   local/slider_form:view  and  local/slider_form:edit   at CONTEXT_SYSTEM
#   'archetypes' => array()
#
# An empty archetype list means no role receives these capabilities on install — not manager,
# not teacher, nobody. Only a site administrator passes has_capability(), and only because
# admins bypass the check entirely. So "role A = manager" would produce an account that is
# denied everything, and the matrix would report a beautifully secure plugin while testing
# nothing. Role A is therefore given the capability EXPLICITLY, through a purpose-made role.
#
# Role B stays a plain authenticated user: the account that must be refused.
#
# Run after `make up TARGET=anuncios_de_plataforma`, once Moodle answers 200.
set -euo pipefail

TARGET=anuncios_de_plataforma
C=seclab_${TARGET}-moodle-1
ENVFILE="targets/$TARGET/target.env"
. "$(dirname "$0")/../../tools/lib-env.sh"

A_USER=$(envget ROLE_A_USER); A_PASS=$(envget ROLE_A_PASS)
B_USER=$(envget ROLE_B_USER); B_PASS=$(envget ROLE_B_PASS)

for v in A_USER A_PASS B_USER B_PASS; do
  [ -n "${!v}" ] || { echo "target.env: $v is empty — nothing to seed" >&2; exit 2; }
done

# The Moodle root differs by recipe: the Bitnami image keeps it at /bitnami/moodle, the
# platform baseline serves the real tree at /var/www/html/zajuna. Detect it rather than hardcode,
# so one seed script serves both and switching recipes does not silently seed nothing.
MROOT=""
for candidate in /var/www/html/zajuna /bitnami/moodle; do
  docker exec "$C" test -f "$candidate/config.php" 2>/dev/null && { MROOT="$candidate"; break; }
done
[ -n "$MROOT" ] || { echo "Moodle is not up: run 'make up TARGET=$TARGET' first" >&2; exit 2; }
echo "moodle root: $MROOT"
# display_errors=0 and `tail -1` are both needed: the real platform ships plugins that emit
# PHP 8.2 deprecation notices on include (local/asistencia among them), and those notices land
# on STDOUT ahead of the value. Capturing them turns $MDATA into a path with a warning glued to
# the front, and the chown below then fails on a filename nobody can read.
MDATA=$(docker exec "$C" php -d display_errors=0 -d error_reporting=0 \
  -r "define('CLI_SCRIPT',true); require('$MROOT/config.php'); echo \$CFG->dataroot;" 2>/dev/null | tail -1)

# The lab's own throwaway passwords are simple on purpose; Moodle's default policy would
# reject them and the seed would fail for a reason that has nothing to do with the audit.
docker exec "$C" php $MROOT/admin/cli/cfg.php --name=passwordpolicy --set=0 >/dev/null 2>&1 || true

docker exec -i -e MROOT="$MROOT" "$C" php -d display_errors=1 /dev/stdin \
  "$A_USER" "$A_PASS" "$B_USER" "$B_PASS" <<'PHP'
<?php
define('CLI_SCRIPT', true);
require(getenv('MROOT').'/config.php');
require_once($CFG->dirroot.'/user/lib.php');
require_once($CFG->libdir.'/accesslib.php');

list(, $auser, $apass, $buser, $bpass) = $argv;

function mkuser($username, $password, $first, $last) {
    global $DB, $CFG;
    if ($u = $DB->get_record('user', ['username' => $username])) {
        echo "exists:  $username (id {$u->id})\n";
        return $u->id;
    }
    $u = new stdClass();
    $u->username = $username;  $u->password = $password;
    $u->firstname = $first;    $u->lastname = $last;
    $u->email = $username.'@lab.local';
    $u->auth = 'manual';       $u->confirmed = 1;
    $u->mnethostid = $CFG->mnet_localhost_id;
    $id = user_create_user($u, true, false);
    echo "created: $username (id $id)\n";
    return $id;
}

$aid = mkuser($auser, $apass, 'Rol', 'Gestor');
$bid = mkuser($buser, $bpass, 'Rol', 'Aprendiz');

// A role that exists only for the audit, holding exactly the two capabilities the plugin
// defines. Not 'manager': borrowing a stock role would also grant dozens of unrelated
// capabilities, and then a 200 would not tell us WHICH permission opened the door.
$ctx = context_system::instance();
$shortname = 'sliderlabmanager';
if (!$roleid = $DB->get_field('role', 'id', ['shortname' => $shortname])) {
    $roleid = create_role('Slider lab manager', $shortname,
        'Audit-only role: exactly the capabilities local_slider_form declares.');
    set_role_contextlevels($roleid, [CONTEXT_SYSTEM]);
    echo "created: role $shortname (id $roleid)\n";
} else {
    echo "exists:  role $shortname (id $roleid)\n";
}

foreach (['local/slider_form:view', 'local/slider_form:edit'] as $cap) {
    if (!$DB->record_exists('capabilities', ['name' => $cap])) {
        // Fail loudly. A silent skip here produces role A with no permissions, every test
        // "denied", and a report that looks like a hardened plugin.
        fwrite(STDERR, "FATAL: capability $cap is not installed — is the plugin present?\n");
        exit(1);
    }
    assign_capability($cap, CAP_ALLOW, $roleid, $ctx->id, true);
    echo "allowed: $cap\n";
}

role_assign($roleid, $aid, $ctx->id);
echo "assigned: $shortname -> $auser (system context)\n";

// Role B gets nothing on purpose: it is the account that must be refused.
$DB->delete_records('role_assignments', ['roleid' => $roleid, 'userid' => $bid]);

// Not accesslib_clear_all_caches_for_unit_testing(): Moodle refuses it outside unit tests
// ("Coding error detected"). A new role assignment is invisible until the access caches are
// dropped, and role A would then be denied everything it was just granted.
purge_all_caches();
echo "done\n";
PHP

# `docker exec` runs as root; Apache does not. purge_all_caches() rebuilds moodledata/cache and
# moodledata/localcache, and whatever it creates is root-owned and unwritable by the web server.
# Moodle then answers EVERY request with a 500 "Invalid permissions detected when trying to
# create a directory" — a message that names permissions but never says whose. Same trap the
# plugin-install hook documents; give the data directory back to its owner.
OWNER=$(docker exec "$C" stat -c '%u:%g' "$MDATA")
docker exec "$C" chown -R "$OWNER" "$MDATA"
echo "moodledata ownership restored to $OWNER"

# El esquema `midb`: las tablas que el plugin consulta fuera de Moodle, con datos sintéticos.
# Va DESPUÉS de crear las cuentas porque una de las filas se atribuye al rol A por username.
# Sin esto, saved_filters y el historial de envíos responden 500 y quedan SIN MEDIR — que no es
# lo mismo que sin hallazgos.
FIXTURE="$(dirname "$0")/../../scenarios/zajunadb-fixture.sql"
if [ -f "$FIXTURE" ]; then
  DBC=seclab_${TARGET}-db-1
  DBN=$(envget DB_NAME); DBU=$(envget DB_USER)
  docker exec -i "$DBC" psql -q -U "$DBU" -d "$DBN" -v ON_ERROR_STOP=1 < "$FIXTURE" >/dev/null \
    && echo "escenario midb aplicado (regionales, centros, saved_filters, envios2)" \
    || echo "AVISO: el escenario midb falló — saved_filters y export_envios darán 500" >&2
fi

echo
echo "Role A = $A_USER  (has local/slider_form:view + :edit at system context)"
echo "Role B = $B_USER  (plain authenticated user — the one that must be denied)"
echo
echo "NOT seeded: slider records, images, envío history. Every plugin screen will therefore"
echo "render its empty state, and a DAST/load run against empty screens measures empty screens."
echo "Record that in RUN.md rather than reading the numbers as coverage of the plugin."
