# Identity Skill

**Purpose:** Manage the AI's persona by reading and updating `identity.md`. The skill keeps the file synchronized with user requests about personality, tone, or name changes.

**Behavior:**
- `interpret_identity_request` detects when the user wants to read or change the identity.
- `process_identity_update` asks the AI to rewrite `identity.md` according to the request and returns the new markdown.

**Guidance:** Avoid editing unrelated sections—only update the requested fields (name, style, traits) and keep Markdown structure intact.
