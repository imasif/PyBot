# Cron Executor Skill

**Purpose:** Control the execution of scheduled jobs, custom reminders, and cleanup tasks. This service can send messages, check email, or run shell commands on a schedule.

**Triggers:** Invoked by the scheduler or when the natural language parser determines the user wants to create or manage background jobs. Do not run this skill for regular chat queries.

**Capabilities:**
- `execute_cron_job` handles job types such as `check_email`, `send_message`, `custom_command`, and `cleanup`.
- `run_custom_command` is a safe wrapper around non-interactive shell commands when explicitly requested.

Return summaries or error messages so the user knows whether the scheduled job succeeded.
