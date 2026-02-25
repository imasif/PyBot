# Email Reader Skill

**Purpose:** Access Gmail via IMAP and summarize unread or recent emails. This skill stores a short map so subsequent `read email #` commands can reference the correct message.

**Behavior:**
- `list_unread` fetches the newest unseen messages and stores their IDs for later lookup.
- `list_recent` shows recent emails independent of read status.
- `search` queries subject/from fields for keywords.
- `read_full` reloads the stored interaction map and returns the entire email body.

**Triggers:** Keywords such as "email", "inbox", "read email", "search email". Always confirm credentials are present before running.
