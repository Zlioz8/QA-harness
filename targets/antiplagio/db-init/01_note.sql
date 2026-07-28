-- Deliberately empty of business data.
--
-- Moodle creates its own schema on first boot, and the plugin's tables come from the plugin's
-- own upgrade step. Anything we wrote here by hand would be a fiction the audit then measures.
--
-- What must NOT go in this directory: a dump of the production Moodle. That database holds
-- learners' names, documents and grades, and the lab's own finding L1 was exactly such a dump
-- becoming reachable from the LAN. Test accounts are created after boot by 02_seed_users.sh,
-- through Moodle's CLI, so they are real Moodle users rather than hand-inserted rows.
SELECT 'antiplagio lab: schema is created by Moodle and by the plugin upgrade, not seeded here';
