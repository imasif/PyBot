# News Skill

**Purpose:** Recognize when the user wants current events or headlines and surface a concise list of articles from NewsAPI.

**Triggers:** Phrases such as "show me the news", "news about", "headlines", or any request mentioning current events.

**Behavior:** `get_news` uses the NewsAPI key (if configured) to fetch either top headlines or search for an explicit topic. Format the result with the title, a short snippet, and the source URL.

**Guidance:** If the API key is missing, return a gentle error message that points the user to the NewsAPI signup page.
