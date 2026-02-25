# Browser Automation Skill

**Purpose:** Drive Brave/Chrome via Selenium so the bot can open web pages, search, or play YouTube content. It is intended for requests such as "play <song> on YouTube" or "open github.com".

**Triggers:** Use when the user explicitly wants the bot to interact with a browser window (YouTube, Google search, opening a link). Avoid running this skill for purely text-based queries.

**Action types:**
- `youtube_play`: open youtube.com, search for the provided query, and attempt to click the first video.
- `web_search`: navigate to Google and execute the supplied query.
- `open_url`: open the exact URL passed in.
- `custom`: visit a URL with extra instructions or automation cues.

**Guidelines:** Keep control of Chrome instances tidy (cleanup temp profiles, kill stray processes) and wait for selectors before clicking. Return a friendly confirmation once the automation starts or if manual intervention is required.
