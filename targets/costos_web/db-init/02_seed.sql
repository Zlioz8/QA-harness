-- Runs AFTER 01_data.sql (the real dump). We do NOT alter real rows; we only add
-- two throwaway accounts with KNOWN passwords so the authenticated DAST/e2e/k6
-- flows can log in. Real users keep their real (unknown) bcrypt hashes.
--
-- Password hash = bcrypt("secret123"); must match ADMIN_PASS/REP_PASS in .env.
-- rol_id 1 = ADMINISTRADOR, 4 = SUBDIRECTOR (representante tier). FKs reference
-- ids that exist in the real dump (regional 2, dependencia 2, grupo 1).

INSERT INTO public.usuarios
  (nombre_completo, email, contrasena, ldap, rol_id, vigencia, estado,
   regional_id, dependencia_id, grupo_id)
VALUES
  ('AUDIT Admin Test','admin@test.local',
   '$2y$10$tMmlutI40NfcWs4UBBXP4ee5hYT5DszExt5/OgBLj7IviGIz.bEwu','audit_admin',
   1, extract(year from now())::int, true, 2, 2, 1),
  ('AUDIT Rep Test','rep@test.local',
   '$2y$10$tMmlutI40NfcWs4UBBXP4ee5hYT5DszExt5/OgBLj7IviGIz.bEwu','audit_rep',
   4, extract(year from now())::int, true, 2, 2, 1);

-- The real dump already contains an active "tiempo" window (2026-06-01..07-31).
-- If auditing outside that range, uncomment to guarantee an active window:
-- INSERT INTO public.tiempo (nombre, fecha_inicio, fecha_fin, estado)
-- VALUES ('AUDIT ventana', now() - interval '1 day', now() + interval '30 day', 'Activo');
