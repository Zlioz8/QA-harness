# `deps/` — inputs the repository does not carry

Mounted read-only at `/deps` by `recipes/php-apache.yml`. The entrypoint uses these only when
the checkout itself does not provide them.

## Why this directory exists at all

`composer.json` and `composer.lock` are listed in ADI's `.gitignore`, so a clean clone does not
contain them and `composer install` fails with *"could not find a composer.json file"*. That is
finding **D1** of `reports/adi/deploy-contract.md`, and it is the reason the lab cannot bring
the application up from the repository alone.

## The `composer.json` here is a RECONSTRUCTION

It was assembled from evidence, not handed over:

- `DEPLOY.md` section 4 names the three direct dependencies: `vlucas/phpdotenv`,
  `phpoffice/phpspreadsheet`, `phpseclib/phpseclib`.
- `docs/AUDITORIA_2026-07-30.md` section 1.2 records the versions observed on the running
  server: `phpdotenv ^5.6`, `phpseclib 3.0.53`, `phpspreadsheet 5.8.0`.
- `composer.json` requires `"php": "^8.0"`; production runs 8.2.

**There is no reconstructed `composer.lock`, on purpose.** Inventing one would produce a file
that looks authoritative and is not, and every CVE then reported would be a fact about this
directory rather than about the deployed application.

## Consequence for the audit, which must appear in the report

The dependency-CVE dimension for ADI is **NOT AUTHORITATIVE**. It describes the versions
Composer happens to resolve here, today, from a reconstructed manifest — not the `vendor/`
tree the team deploys. A clean result here is *not* evidence of a clean dependency tree.

This stops being true the moment the team supplies the real files:

1. Ask the developer responsible (Juan David Solano) for the `composer.json` and
   `composer.lock` from the running server (`/var/www/html/adi/`).
2. Drop both in this directory, replacing the reconstruction.
3. Delete the NOT AUTHORITATIVE caveat from the report and re-run.

The durable fix belongs in their repository: commit both files and remove them from
`.gitignore`. A lock file is not a secret — it is the only record of what actually runs.

## `.env`

Not present, and should not be. `php-apache`'s entrypoint falls back to the repository's own
`.env.example` and repoints the database hosts named in `DB_HOST_VARS`. Copying the real
server's `.env` here would import production credentials into the lab, which the data policy
forbids and which no measurement requires.
