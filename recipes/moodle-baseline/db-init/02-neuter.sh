#!/bin/bash
# Neutralise the copy. Runs immediately after the restore, BEFORE the web server is ever reachable.
#
# This is not hygiene. A faithful mirror of a platform is a loaded weapon pointed at whatever the
# original could reach, and the lab's whole job is to attack it:
#
#   * The plugin under audit (local_slider_form) SENDS MASS EMAIL to everyone enrolled in the
#     courses it resolves. `make dast` and `make perf` exist to hammer endpoints. A copy that
#     kept working SMTP would mail thousands of addresses the first time a scanner found
#     ajax/send_segmented.php. Synthetic-looking addresses do not help: an address at gmail.com
#     is delivered by gmail.com regardless of who invented it.
#   * Web-service tokens in the dump are still valid AGAINST THE ORIGINAL SERVER. A copy running
#     unauthenticated on a laptop must not carry live keys to the real platform.
#   * wwwroot points at the production hostname. Moodle redirects every request there, which
#     looks exactly like "the container is broken" and costs an afternoon to diagnose.
#
# Fails the whole startup if any of it fails: serving the copy un-neutered is worse than not
# serving it at all.
set -euo pipefail

echo "[baseline] neutralising the copy"

psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" <<SQL
-- 1. Outbound mail: off at the root. noemailever is the switch Moodle honours everywhere,
--    including from cron and from ad-hoc tasks the plugin might queue.
INSERT INTO mdl_config (name, value) VALUES ('noemailever', '1')
  ON CONFLICT (name) DO UPDATE SET value = '1';
UPDATE mdl_config SET value = '' WHERE name IN ('smtphosts','smtpuser','smtppass','supportemail');

-- 2. wwwroot: the copy answers here, not at the production hostname.
UPDATE mdl_config SET value = '${MOODLE_WWWROOT}' WHERE name = 'wwwroot';

-- 3. Any setting still carrying the production hostname would send a browser back there
--    mid-session. alternateloginurl is the one that bites first.
UPDATE mdl_config SET value = '' WHERE name IN ('alternateloginurl','forgottenpasswordurl');

-- 4. Live credentials to the original platform. Not needed by any audit.
DELETE FROM mdl_external_tokens;
DELETE FROM mdl_user_private_key;

-- 5. Sessions inherited from the dump: they would authenticate as whoever was logged in.
DELETE FROM mdl_sessions;

-- 6. Scheduled tasks: a mirror must not run the platform's cron. Disabling them stops the copy
--    from, say, retrying a queued message send the moment it boots.
UPDATE mdl_task_scheduled SET disabled = 1;

-- 7. Debugging on: the audit wants the real error, not a friendly page. This is a deliberate
--    weakening and is exactly why this copy never leaves loopback.
INSERT INTO mdl_config (name, value) VALUES ('debug', '32767')
  ON CONFLICT (name) DO UPDATE SET value = '32767';
INSERT INTO mdl_config (name, value) VALUES ('debugdisplay', '1')
  ON CONFLICT (name) DO UPDATE SET value = '1';
SQL

echo "[baseline] mail disabled · tokens dropped · sessions cleared · wwwroot=${MOODLE_WWWROOT}"
