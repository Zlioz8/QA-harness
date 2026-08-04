# recipes/ — reusable runtime blocks

A target's `compose.runtime.yml` answers one question: **how does this app come up?**
That question repeats across projects far more than it varies, so the answers live here as
parameterised compose fragments and a target *composes* them instead of writing Docker.

```yaml
# targets/<name>/compose.runtime.yml
# Paths resolve against the PROJECT directory (the lab root), not against this file.
include:
  - path: ./recipes/postgres.yml
  - path: ./recipes/moodle-plugin.yml
services: {}   # target-specific extras go here
```

Everything a recipe needs comes from `target.env`, so the recipe itself stays project-blind.
Adding a recipe is the only cost of onboarding a stack the lab has never seen — and it is paid
once, by the first project on that stack.

| Recipe | Brings up | Reads from target.env |
|---|---|---|
| `postgres.yml` | PostgreSQL + `db-init/*.sql` on first boot | `DB_IMAGE DB_NAME DB_USER DB_PASSWORD TARGET_NAME` |
| `moodle-plugin.yml` | A Moodle serving a plugin that has no entry point of its own | `MOODLE_IMAGE MOODLE_PORT PLUGIN_SUBDIR PLUGIN_COMPONENT PLUGIN_TYPE ROLE_A_* DB_*` |
| `moodle-baseline.yml` | The platform's **own** Moodle, restored ephemeral from `baselines/<name>/` and neutralised before the port opens. Use it instead of `moodle-plugin.yml` when the platform version is what you are auditing against | `MOODLE_BASELINE MOODLE_PORT MOODLE_WWWROOT MOODLE_ADMIN_* DB_*` |
| `fastapi-uvicorn.yml` | A FastAPI/uvicorn service from a source subdir | `API_SUBDIR API_MODULE API_PORT PYTHON_IMAGE` |
| `kafka-zk.yml` | Kafka + Zookeeper for pipelines that need a broker | `KAFKA_IMAGE ZK_IMAGE` |

Rules every recipe follows, without exception:

- The audited source is mounted **read-only**. If the runtime needs to write (install
  dependencies, generate a key), it copies into a container-local path first.
- Published ports bind to **`127.0.0.1`**. The lab may hold real data; `0.0.0.0` hands it to
  the whole LAN (lab finding L1).
- Nothing is hardcoded to a project. A literal project name in a recipe is a bug.
- Resource limits are declared when the recipe is meant for load testing, so a breaking point
  is attributable to a stated envelope.
