# Information Search Skill

**Purpose:** Detect general web queries or references to Wikipedia and supply concise summaries.

**Behavior:**
- `detect_search_request` matches patterns such as "search", "look up", or question words followed by a topic.
- `search_web` performs a DuckDuckGo search and formats the top results with titles, snippets, and URLs.
- `detect_wikipedia_request` isolates Wikipedia-style inquiries.
- `search_wikipedia` reads the Wikipedia summary and returns a short article preview.

**Guidance:** Prioritize this skill when the user asks for facts or definitions not covered by other features. Avoid triggering on personal identity questions or planner commands.
