# Jarvis AI Bot - Feature Guide

## 🌟 Complete Feature List

### 1. Weather & Information
**Weather Forecasts:**
- "What's the weather?"
- "Weather in Tokyo"
- "How's the weather in London?"

**Web Search:**
- "Search for Python tutorials"
- "Who is Elon Musk?"
- "What is quantum computing?"

**Wikipedia:**
- "Tell me about Albert Einstein"
- "Wikipedia for artificial intelligence"

**News:**
- "Show me the news"
- "News about technology"
- "Latest headlines"

**Daily Briefing:**
- "Give me my daily briefing"
- "Morning briefing"
- "Brief me"

### 2. Productivity Tools
**Notes & Memos:**
- "Create a note: Buy groceries tomorrow"
- "Note this: Meeting with client at 3pm"
- "List my notes"
- "Search notes for meeting"

**Timers:**
- "Set timer for 10 minutes"
- "Timer for 1 hour 30 minutes"
- "Show my timers"

**Shopping Lists:**
- "Add milk to shopping list"
- "Add eggs, bread, and butter to shopping list"
- "Show shopping list"
- "Buy 3 apples and 2 oranges"

**Calculations & Conversions:**
- "Calculate 25 + 37"
- "Convert 100 fahrenheit to celsius"
- "How many meters in 5 kilometers"
- "What is 50% of 200"

### 3. Email Management
**Check Emails:**
- "Check my unread emails"
- "Show my recent emails"
- "Last 10 emails"

**Search Emails:**
- "Search emails about meeting"
- "Find emails from John"

**Read Specific Emails:**
- "Read email #3"
- "Show email number 5"

### 4. Task Scheduling & Reminders
**One-Time Reminders:**
- "Remind me to call Mom at 5pm"
- "Set a reminder to exercise in 1 hour"
- "Remind me to check the oven in 30 minutes"

**Recurring Schedules:**
- "Remind me to drink water every 2 hours"
- "Send me a message every morning at 8am"
- "Schedule a backup every day at midnight"

**Manage Scheduled Tasks:**
- "List my jobs" (shows all reminders and schedules)
- "Delete the water reminder job"
- "Disable morning reminder"
- "Enable backup job"
- "Edit water reminder to every 3 hours"

### 5. Life Tracking
**Sleep Tracking:**
- "Good night" (bedtime)
- "Good morning" (wake time)
- "Give me a sleep report for last week"

**Activity Tracking:**
- "Logged 30 minutes of exercise"
- "Studied for 2 hours"
- "Drank 500ml water"
- "Mood: happy"
- "Generate my exercise report"

### 6. Browser Automation
**Open URLs:**
- "Open youtube.com"
- "Go to github.com"

**YouTube:**
- "Play Love Song by Selena Gomez on YouTube"
- "Open YouTube and find Python tutorials"

**Google Search:**
- "Google search for restaurants near me"

### 7. System Commands
**Auto-Resolved Queries:**
- "What's the current time?"
- "What's the date today?"
- "Show disk space"
- "What's my IP address?"
- "Memory usage"

**Custom Commands:**
- "Run command: ls -la"
- "Execute: ps aux | grep python"

### 8. AI Chat
Just talk naturally! I understand context and can help with:
- Questions and answers
- Explanations
- Recommendations
- General conversation

### 9. 🎓 AI Learning System
**The bot learns YOUR unique way of speaking!**

The more you use features, the better the bot understands your personal phrasing. It automatically saves successful patterns and uses them to recognize your requests faster next time.

**How It Works:**
1. When you successfully use a feature (e.g., weather, notes, timers), the bot saves your phrasing
2. Next time, it checks your learned patterns BEFORE trying regex matching
3. Each time you use the same pattern, confidence increases
4. The bot adapts to how YOU like to communicate

**What Gets Learned:**
- Weather queries: "weather London" → "London weather update"
- Notes: "jot this down" → "note:"
- Shopping: "get milk" → "shopping: milk"
- Timers: "countdown 5 min" → "timer 5m"
- Time queries: "what time is it" → "time?" ⭐ NEW!
- News: "headlines" → "news brief"
- Wikipedia: "wiki Einstein" → "about Einstein"
- Searches: "look up cats" → "search cats"
- Status: "how are you" → "status check"
- Briefings: "morning update" → "briefing"

**View Your Learning Progress:**
```
/learned
```
This shows:
- All patterns the bot has learned from you
- Confidence levels (🟢 High, 🟡 Medium, 🔴 Low)
- How many times you've used each pattern
- Grouped by feature type

**Example Learning Flow:**
```
You: "what's the weather in Paris"
Bot: [Shows Paris weather, learns pattern]

You: "paris weather"  
Bot: [Recognizes from learned patterns - faster!]

You: "how's paris looking"
Bot: [Learns this variation too]

/learned
📊 Learned Patterns:

Weather (3 patterns):
  🟢 "paris weather" → weather:Paris (used 5 times, confidence: 1.0)
  🟡 "weather in paris" → weather:Paris (used 2 times, confidence: 0.7)
  🟡 "how's paris looking" → weather:Paris (used 1 time, confidence: 0.6)
```

**Privacy:**
- Learned patterns are stored locally in your database
- Each user has their own learning profile
- Your patterns don't affect other users
- You can view all stored patterns anytime with `/learned`

**Benefits:**
- ✅ Faster response times (database lookup vs regex matching)
- ✅ More accurate detection for YOUR style
- ✅ Bot adapts to regional phrases and slang
- ✅ Personalized experience that improves over time
- ✅ Works across all major features

## 🔌 Modular Skills

Each bot capability is defined as a skill under `skills/<slug>` with a `metadata.json` file for machine-readable configuration and an `instructions.md` file for human-readable guidance. The loader at `services/plugin_registry.py` reads those files and instantiates the requested class so you can plug new services simply by dropping paired JSON/Markdown definitions.

## 🔧 Setup Required

### API Keys (Optional but Recommended)
Add these to your `.env` file:

```env
# Weather (free from openweathermap.org)
OPENWEATHER_API_KEY=your_key_here
DEFAULT_CITY=London
DEFAULT_COUNTRY_CODE=GB

# News (free from newsapi.org)
NEWSAPI_KEY=your_key_here
```

Without these keys, weather and news features won't work, but everything else will!

## 💡 Tips
1. **Be Natural**: You can phrase things casually - I understand context
2. **Multiple Items**: For shopping lists, separate items with commas or "and"
3. **Time Formats**: I understand "in 1 hour", "at 3pm", "tomorrow at 9am", etc.
4. **Reports**: Use tracking features for a week, then ask for reports
5. **Cron Jobs**: Use natural language - I'll convert to proper scheduling

## 🎯 Coming Soon
- Calendar integration
- Voice commands
- Contact management
- File management
- Smart home integration
- More languages

## 🆘 Getting Help
- "What can you do?" - See all capabilities
- "Help me" - General assistance
- Use /start command - See basic commands
