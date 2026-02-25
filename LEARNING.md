# 🎓 AI Learning System - Teaching Your Bot

## Overview
Your Jarvis bot has an AI learning system that adapts to YOUR unique way of speaking. The more you use it, the better it understands you.

## How It Works

### Automatic Learning
Every time you successfully use a feature, the bot:
1. **Saves your exact phrasing** to its learning database
2. **Associates it** with the detected intent (e.g., "weather:Paris")
3. **Builds confidence** - each repeated use increases from 0.5 to 1.0
4. **Speeds up detection** - checks learned patterns BEFORE regex matching

### What Gets Learned
- ✅ **Weather queries**: "weather London" → learns "London weather"
- ✅ **Notes**: "jot this down" → learns "note creation"
- ✅ **Shopping**: "get milk" → learns "shopping: milk"
- ✅ **Timers**: "countdown 5 min" → learns "timer 5m"
- ✅ **Time queries**: "what time is it" → learns "time?" ⭐ NEW!
- ✅ **News**: "headlines" → learns "news brief"
- ✅ **Wikipedia**: "wiki Einstein" → learns "about Einstein"
- ✅ **Searches**: "look up cats" → learns "search cats"
- ✅ **Status**: "how are you" → learns "status check"
- ✅ **Briefings**: "morning update" → learns "briefing"

## Teaching the Bot

### Method 1: Just Use It Naturally
The easiest way to teach the bot is to simply use features the way YOU naturally speak:

```
You: "what's the weather in Paris"
Bot: [Shows Paris weather] ✅ Learned!

You: "paris weather"  
Bot: [Uses learned pattern - faster response!]

You: "how's paris looking"  
Bot: [Learns this variation too]
```

After a few uses, the bot knows that when YOU say "paris weather" or "how's paris looking", you want Paris weather data.

### Method 2: Repetition Increases Confidence
The more you use a phrase, the higher its confidence:

- 1st use: **0.5 confidence** (🔴 Low)
- 2nd use: **0.6 confidence** (🔴 Low)
- 3rd use: **0.7 confidence** (🟡 Medium)
- 4th use: **0.8 confidence** (🟡 Medium)
- 5th use: **0.9 confidence** (🟢 High)
- 6th+ uses: **1.0 confidence** (🟢 High - Maximum!)

Higher confidence = faster detection and more reliable pattern matching.

### Method 3: View Your Progress
Use the `/learned` command anytime to see what the bot has learned:

```
/learned

📊 Learned Patterns:

Weather (3 patterns):
  🟢 "paris weather" → weather:Paris (used 5 times, confidence: 1.0)
  🟡 "weather in paris" → weather:Paris (used 2 times, confidence: 0.7)
  🟡 "how's paris looking" → weather:Paris (used 1 time, confidence: 0.6)

Notes (2 patterns):
  🟢 "jot this down" → notes_create (used 6 times, confidence: 1.0)
  🔴 "write it down" → notes_create (used 1 time, confidence: 0.6)

...
```

## Correcting the Bot

### If the Bot Misunderstands
Currently, the learning system only saves **successful** detections. If the bot gets it wrong:

1. **Rephrase your request** using clearer wording
2. **Use explicit keywords** that match the feature:
   - For weather: "weather in [city]"
   - For notes: "create a note: [content]"
   - For shopping: "add [item] to shopping list"
   - For timers: "set timer for [duration]"

### Future Enhancement (Coming Soon)
A correction feature will allow you to:
- Say "no, I meant [correct interpretation]"
- Bot removes the incorrect pattern
- Bot learns the correct association

## Privacy & Data

### Where Is Data Stored?
- **Local SQLite database**: `MyPyBot.db`
- **Tables**: `learned_patterns` and `user_context`
- **Per-user**: Your patterns don't affect other users
- **No cloud**: Everything stays on your server

### What's Stored?

**learned_patterns table:**
```sql
- user_id: Your Telegram ID
- pattern_type: Feature category (weather, notes, shopping, etc.)
- user_input: Your exact phrasing (e.g., "paris weather")
- detected_intent: What the bot understood (e.g., "weather:Paris")
- confidence: 0.5 to 1.0
- success_count: How many times you've used this pattern
- created_at: When first learned
- last_used_at: When last used
```

**user_context table:**
```sql
- user_id: Your Telegram ID
- context_key: Preference name (e.g., "greeting_style")
- context_value: Preference value (e.g., "casual")
- created_at: When created
- updated_at: When last updated
```

### Viewing/Deleting Your Data
To see all learned data:
```bash
sqlite3 MyPyBot.db "SELECT * FROM learned_patterns WHERE user_id='YOUR_TELEGRAM_ID';"
```

To delete all your learned patterns:
```bash
sqlite3 MyPyBot.db "DELETE FROM learned_patterns WHERE user_id='YOUR_TELEGRAM_ID';"
```

## Examples

### Example 1: Teaching Weather Preferences
```
Day 1:
You: "what's the weather in London"
Bot: [Shows London weather, confidence: 0.5]

You: "london weather"
Bot: [Shows London weather, confidence: 0.6]

Day 3:
You: "how's london"
Bot: [Shows London weather, confidence: 0.6]

After 1 week:
/learned shows:
  🟢 "london weather" → weather:London (8 uses, confidence: 1.0)
  🟡 "what's the weather in london" → weather:London (3 uses, confidence: 0.8)
  🟡 "how's london" → weather:London (2 uses, confidence: 0.7)
```

### Example 2: Teaching Note-Taking Style
```
You: "remember this: buy milk"
Bot: [Creates note, confidence: 0.5]

You: "jot down: meeting at 3pm"
Bot: [Creates note, confidence: 0.5]

You: "note: call mom"
Bot: [Creates note, confidence: 0.5]

After several uses:
/learned shows:
  🟢 "jot down:" → notes_create (10 uses, confidence: 1.0)
  🟡 "note:" → notes_create (5 uses, confidence: 1.0)
  🟡 "remember this:" → notes_create (3 uses, confidence: 0.8)
```

### Example 3: Teaching Time Query Style
```
You: "what time is it"
Bot: [Shows current time, confidence: 0.5]

You: "time?"
Bot: [Shows current time, confidence: 0.6]

You: "time please"
Bot: [Shows current time, confidence: 0.7]

After several uses:
/learned shows:
  🟢 "time?" → time_query (12 uses, confidence: 1.0)
  🟢 "what time is it" → time_query (8 uses, confidence: 1.0)
  🟡 "time please" → time_query (4 uses, confidence: 0.9)
```

## Tips for Faster Learning

1. **Be Consistent**: Use similar phrases for the same action
2. **Short & Sweet**: "paris weather" learns faster than full sentences
3. **Repeat Often**: Use features daily to build confidence quickly
4. **Check Progress**: Use `/learned` weekly to see what stuck
5. **Mix It Up**: The bot learns variations too - don't be too rigid

## Technical Details

### Learning Algorithm
1. **First Detection**: Confidence starts at 0.5
2. **Each Reuse**: Confidence += 0.1 (max 1.0)
3. **Fuzzy Matching**: Checks if your input contains learned pattern OR vice versa
4. **Priority**: Learned patterns checked BEFORE regex patterns
5. **Speed**: Database lookup (~1ms) vs regex matching (~10-50ms)

### Supported Features
Currently learns for:
- ✅ Weather detection
- ✅ Note creation/listing/searching
- ✅ Shopping list management
- ✅ Timer creation/listing
- ✅ Time queries (what time is it)
- ✅ Wikipedia queries
- ✅ Web searches
- ✅ News requests
- ✅ Status checks
- ✅ Daily briefings

### Future Enhancements
- 🔜 Correction mechanism ("no, I meant...")
- 🔜 Synonym detection (learn that "jot" = "note" = "write")
- 🔜 Multi-language support
- 🔜 Export/import learned patterns
- 🔜 Negative pattern learning (what NOT to match)

## FAQs

**Q: Does learning affect other users?**  
A: No! Each user has a completely separate learning profile.

**Q: Can I reset my learned patterns?**  
A: Yes, use SQL to delete from `learned_patterns` table, or we can add a `/forget` command.

**Q: How much data gets stored?**  
A: Very minimal - just your phrases and what they matched. Typical user: <1KB after months.

**Q: Does it slow down the bot?**  
A: No! It actually makes the bot FASTER because database lookups are quicker than regex matching.

**Q: What if I change how I phrase things?**  
A: The bot will learn the new patterns too. Old patterns stay in the database but won't be used.

**Q: Can I teach it slang or regional phrases?**  
A: Absolutely! If you say "innit weather in london bruv" and it works, the bot will learn that's how YOU ask for weather.

## Commands Reference

- `/learned` - View all learned patterns and confidence levels
- `/status` - Shows learning statistics (total patterns, preferences)

## Support

For questions or issues with the learning system:
1. Check this documentation
2. Use `/learned` to see what's stored
3. Try rephrasing with explicit keywords
4. Report persistent issues on GitHub

---

**Remember:** The bot learns from YOU! The more you use it naturally, the smarter it becomes at understanding YOUR unique communication style. 🎓✨
