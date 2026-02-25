# Notes Skill

**Purpose:** Capture quick notes, list what has been saved, or search note content.

**Behavior:**
- `detect_request` looks for phrases like "create a note", "remember", or "list my notes" and optionally learns the user's phrasing.
- `create_note` asks the AI to suggest a title/content pair and writes it to the database.
- `list_notes` shows up to ten recent entries with previews.
- `search_notes` scans past notes for keywords.

**Guidance:** Trigger only when the user explicitly wants note-taking or discovery, avoiding confusion with tasks or reminders.
