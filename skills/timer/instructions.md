# Timer Skill

**Purpose:** Start countdown timers and show active timers when asked.

**Behavior:**
- `detect_request` matches phrases like "set timer for 10 minutes" or "countdown" and records the duration.
- `create_timer` parses hours/minutes/seconds, stores the timer, and returns the confirmed duration.
- `list_timers` displays current timers, estimating remaining time.

**Guidance:** Only run this skill for explicit timer requests. Do not confuse it with scheduling reminders or cron jobs.
