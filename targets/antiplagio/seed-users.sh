#!/usr/bin/env bash
# Create the two accounts the authorization matrix needs, through Moodle's own CLI.
#
# Why not INSERT them: Moodle users carry password hashing, auth plugin, capabilities and
# enrolments. A hand-inserted row logs in badly or not at all, and then a failed authorization
# test means "the seed was wrong", not "the application is safe" — the worst possible outcome
# for an audit, because it looks like a pass.
#
# Run after `make up TARGET=antiplagio`, once Moodle answers 200.
set -euo pipefail
C=seclab_antiplagio-moodle-1
ENVFILE="targets/antiplagio/target.env"
get() { sed -n "s/^${1}=//p" "$ENVFILE" | tail -1; }

A_USER=$(get ROLE_A_USER); A_PASS=$(get ROLE_A_PASS)
B_USER=$(get ROLE_B_USER); B_PASS=$(get ROLE_B_PASS)

mk() {  # mk <username> <password> <firstname> <lastname>
  docker exec "$C" php /bitnami/moodle/admin/cli/cfg.php --name=passwordpolicy --set=0 >/dev/null 2>&1 || true
  docker exec "$C" php -r "
    define('CLI_SCRIPT', true);
    require('/bitnami/moodle/config.php');
    require_once(\$CFG->dirroot.'/user/lib.php');
    if (\$DB->record_exists('user', ['username' => '$1'])) { echo \"exists: $1\n\"; exit(0); }
    \$u = new stdClass();
    \$u->username = '$1'; \$u->password = '$2';
    \$u->firstname = '$3'; \$u->lastname = '$4';
    \$u->email = '$1@lab.local'; \$u->auth = 'manual';
    \$u->confirmed = 1; \$u->mnethostid = \$CFG->mnet_localhost_id;
    \$id = user_create_user(\$u, true, false);
    echo \"created: $1 (id \$id)\n\";
  "
}

mk "$A_USER" "$A_PASS" Rol Instructor
mk "$B_USER" "$B_PASS" Rol Aprendiz

echo
echo "Role A = $A_USER (high privilege) · Role B = $B_USER (low privilege)"
echo "Both are plain site users so far. Enrolling them in a course with the instructor/student"
echo "roles is what makes the authorization matrix meaningful — until then, a 403 for role A"
echo "proves nothing about the plugin's checks."
