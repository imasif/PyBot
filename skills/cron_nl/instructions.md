# Natural Language Scheduler Skill

**Purpose:** Use the AI to translate scheduling requests into cron job definitions and manage them when users mention jobs.

**Behavior:**
- `parse_cron_from_text` returns structured JSON describing a job type, parameters, and schedule.
- `create_cron_from_natural_language` converts chat requests into cron data, saves it, and attempts to register the job.
- `manage_cron_job_nl` interprets follow-up commands such as list, pause, enable, disable, delete, or edit a job.

**Guidance:** Only trigger when the user explicitly wants a reminder, recurring message, or when they mention cron management. Do not run for unrelated chat.
