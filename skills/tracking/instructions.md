# Tracking Skill

**Purpose:** Track habits, workouts, mood, sleep, and other custom activities, then generate reports when requested.

**Behaviors:**
- Detect phrases like "logged", "track", or "report" to decide whether to log an event or summarize data.
- `interpret_tracking_request` extracts category, value, units, and optional reporting schedule using the AI helper.
- `generate_tracking_report` and `generate_sleep_report` build narrative summaries with averages and tips.

**Guidance:** Only log an event when the user clearly indicates they performed an activity. For report requests, mention the category and timeframe to make summaries useful.
