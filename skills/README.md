# Service Skills

Each service that powers the bot is defined as a skill:

1. `metadata.json` contains the machine-readable definition (slug, module, class, keywords).
2. `instructions.md` describes the human-readable behavior, triggers, and capabilities.

To introduce a new skill:

- Create a dedicated folder under `skills/<slug>`.
- Provide `metadata.json` with `module`, `class`, and optional `keywords`, `init_args`, or `init_kwargs`.
- Register command exports inside the service module using `SERVICE_SKILL_COMMANDS = [...]` (or class-level `SKILL_COMMANDS = [...]`).
- Run `sync_skill_metadata_commands()` (or enable auto-sync on startup) to propagate service-declared commands into each skill `metadata.json`.
- Write `instructions.md` that explains how the skill should behave and when it should trigger.
- Restart the bot; the `plugin_registry` loader will automatically import and instantiate the new skill.

Keeping metadata and documentation together makes the service architecture pluggable and easy to extend.
