# Shopping List Skill

**Purpose:** Keep a persistent shopping list, add new items (with optional quantities), show the list, and clear purchased entries.

**Behavior:**
- `detect_request` watches for commands like "add milk to shopping list", "buy", or "show shopping list".
- `add_items` splits comma-separated input into clean entries and stores them with optional quantities.
- `list_items` returns the current contents with item IDs.
- `clear_items` removes purchased rows to keep the list fresh.

**Guidance:** Use this skill when the user is clearly composing or consulting a shopping list. Do not mix it with timer or reminder intents.
