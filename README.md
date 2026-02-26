# PyBot - Your Complete Personal Assistant 🤖

A powerful Telegram-based AI personal assistant with **19 core features** including weather forecasts, notes, reminders, shopping lists, web search, news, email management, task scheduling, life tracking, browser automation, and **AI learning that adapts to YOUR unique communication style**.

## 🌟 Key Features

### 🎓 AI Learning System (NEW!)
- **Personalized Understanding** - Learns YOUR unique way of speaking
- **Pattern Recognition** - Saves successful interactions for faster detection
- **Confidence Building** - Gets smarter with each use
- **Privacy-First** - All learning stored locally per user
- **View Progress** - `/learned` command shows what the bot knows about you

### 📊 Information & Knowledge
- **Weather Forecasts** - Real-time weather for any location
- **Web Search** - DuckDuckGo powered search
- **Wikipedia** - Instant knowledge lookup
- **News Briefings** - Top headlines and topic-specific news
- **Daily Briefings** - Combined weather + news + reminders

### 📝 Productivity Tools
- **Notes & Memos** - Create, search, and organize notes
- **Timers** - Multiple countdown timers
- **Shopping Lists** - Smart item tracking with quantities
- **Calculator** - Math operations and unit conversions

### 📧 Communication
- **Email Management** - Read, search, and monitor Gmail
- **Smart Replies** - Natural language email interaction

### ⏰ Task Scheduling & Reminders
- **One-Time Reminders** - "Remind me in 2 hours", "at 3pm tomorrow"
- **Recurring Schedules** - "Every day at 9am", "every 2 hours from 6pm to 5am"
- **Automated Tasks** - Schedule any command or action
- **Report Generation** - Scheduled tracking reports

### 📊 Life Tracking
- **Sleep Tracking** - Bedtime/wake logging with reports
- **Activity Tracking** - Exercise, study, mood, habits
- **Custom Categories** - Track anything you want
- **Automated Reports** - Weekly/monthly insights

### 🌐 Browser Automation
- **YouTube Auto-Play** - Ad-skipping included
- **URL Opening** - Any website
- **Google Search** - Direct browser searches
- **Chrome Management** - Instance cleanup

### 🔧 System Control
- **Command Execution** - Natural language to shell commands
- **Auto-Resolved Queries** - Time, date, disk space, IP, etc.
- **OS-Aware** - Works on Linux, Mac, Windows

### 🤖 AI Chat
- **Context Retention** - Remembers conversation history
- **Natural Language** - Talk casually, I understand
- **Identity Awareness** - Personalized responses

## 🚀 Quick Start

For full setup + binary build instructions, see [INSTALL.md](INSTALL.md).

### Built-in Onboarding and Gateway Commands

Onboarding is handled by bash script:

```bash
./scripts/onboarding.sh
```

The binary `onboard` command delegates to that script:

```bash
./dist/pybot/pybot onboard
./dist/pybot/pybot gateway list
./dist/pybot/pybot gateway set OPENWEATHER_API_KEY <your_key>
```

From Telegram chat you can also edit config using:
- `/setconfig KEY VALUE`
- `/gateway set KEY VALUE`

### Download Prebuilt Binaries (GitHub Releases)

Each tagged release publishes these assets automatically via GitHub Actions:

- `pybot-linux.tar.gz` + `pybot-linux.tar.gz.sha256`
- `pybot-macos.tar.gz` + `pybot-macos.tar.gz.sha256`
- `pybot-windows.zip` + `pybot-windows.zip.sha256`

Download from your repository’s **Releases** page, then verify checksum.

**Linux/macOS:**
```bash
sha256sum -c pybot-linux.tar.gz.sha256
# or
sha256sum -c pybot-macos.tar.gz.sha256
```

**Windows (PowerShell):**
```powershell
Get-FileHash .\pybot-windows.zip -Algorithm SHA256
# compare the hash with pybot-windows.zip.sha256
```

Run binary after extracting:

```bash
./pybot/pybot
```

### Prerequisites
- Python 3.12+
- Telegram Bot Token (from [@BotFather](https://t.me/BotFather))
- Ollama with llama3.2 model (or OpenAI API)

### Installation

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd PyBot
   ```

2. **Create virtual environment**
   ```bash
   python -m venv env
   source env/bin/activate  # On Windows: env\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment**
   ```bash
   cp .env.example .env
   # Edit .env with your credentials
   ```

5. **Run the bot**
   ```bash
   python bot.py
   ```

## ⚙️ Configuration

### Required Settings (.env)
```env
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
CRON_NOTIFY_USER_ID=your_telegram_user_id
AI_BACKEND=ollama
OLLAMA_URL=http://127.0.0.1:11434/api/generate
OLLAMA_MODEL=llama3.2
```

### Optional APIs (Recommended)
```env
# Weather (free from openweathermap.org)
OPENWEATHER_API_KEY=your_key_here
DEFAULT_CITY=London

# News (free from newsapi.org)
NEWSAPI_KEY=your_key_here

# Gmail (for email features)
GMAIL_EMAIL=your_email@gmail.com
GMAIL_APP_PASSWORD=your_app_password

# Discord bridge (optional)
DISCORD_BOT_TOKEN=your_discord_bot_token
DISCORD_ALLOWED_CHANNEL_IDS=123456789012345678,987654321098765432

# Universal semantic NLU fallback (optional)
NLU_ENABLED=true
NLU_MODEL=sentence-transformers/all-MiniLM-L6-v2
NLU_MIN_CONFIDENCE=0.22

# WhatsApp bridge via Twilio (optional)
WHATSAPP_TWILIO_ACCOUNT_SID=your_twilio_account_sid
WHATSAPP_TWILIO_AUTH_TOKEN=your_twilio_auth_token
WHATSAPP_TWILIO_NUMBER=whatsapp:+14155238886
WHATSAPP_WEBHOOK_VERIFY_TOKEN=your_random_verify_token
```

### Discord + WhatsApp Bridge
- Discord: set `DISCORD_BOT_TOKEN`; the bot listens to channel messages and replies using the same AI context pipeline.
- Optional channel restriction: set `DISCORD_ALLOWED_CHANNEL_IDS` (comma-separated).
- WhatsApp: configure your Twilio Sandbox/number webhook to:
   - `POST https://<your-public-domain>/webhook/whatsapp?token=<WHATSAPP_WEBHOOK_VERIFY_TOKEN>`
- Inbound WhatsApp messages are processed through the same AI context pipeline and saved in `messages` table with platform `whatsapp`.

## 📚 Usage Examples

### Weather
```
"What's the weather?"
"Weather in Tokyo"
"Is it going to rain today?"
```

### Notes
```
"Create a note: Project deadline is next Friday"
"List my notes"
"Search notes for meeting"
```

### Task Scheduling & Reminders
```
"Remind me to call Mom at 5pm"
"Set a reminder to exercise in 1 hour"
"Remind me to drink water every 2 hours"
"Send me a message every morning at 8am"
"List my jobs"
"Delete the water reminder job"
```

### Shopping Lists
```
"Add milk to shopping list"
"Add eggs, bread, and butter to shopping list"
"Show shopping list"
```

### Web Search & Knowledge
```
"Search for Python tutorials"
"Who is Elon Musk?"
"Tell me about quantum computing"
"Show me tech news"
```

### Life Tracking
```
"Good night" (logs bedtime)
"Good morning" (logs wake time)
"Logged 30 minutes of exercise"
"Generate my sleep report for last week"
```

### Browser Automation
```
"Play Love Song by Selena Gomez on YouTube"
"Open github.com"
"Google search for restaurants near me"
```

See [FEATURES.md](FEATURES.md) for complete feature list and examples.

## 🗄️ Database

SQLite database (`MyPyBot.db`) with tables:
- `messages` - Chat history
- `config` - Settings
- `cron_jobs` - Scheduled tasks (includes reminders)
- `sleep_logs` - Sleep tracking
- `tracking_logs` - Activity tracking
- `notes` - User notes
- `shopping_items` - Shopping lists
- `timers` - Countdown timers

## 🔒 API Keys Setup

### Free API Keys

1. **OpenWeatherMap** (Weather)
   - Sign up: https://openweathermap.org/api
   - Free tier: 1000 calls/day
   - Add to `.env`: `OPENWEATHER_API_KEY=xxx`

2. **NewsAPI** (News)
   - Sign up: https://newsapi.org/
   - Free tier: 100 requests/day
   - Add to `.env`: `NEWSAPI_KEY=xxx`

3. **Gmail App Password** (Email)
   - Go to: https://myaccount.google.com/apppasswords
   - Create password for "Mail"
   - Add to `.env`: `GMAIL_APP_PASSWORD=xxx`

### No API Key Needed
- DuckDuckGo Search ✅
- Wikipedia ✅
- Notes, Timers, Shopping Lists ✅
- Calculator ✅

## 📂 Project Structure

```
MyPyBot/
├── bot.py                      # Main bot code (3200+ lines)
├── database.py                 # Database operations (650+ lines)
├── config.py                   # Configuration loader
├── identity.md                 # Bot personality
├── .env                        # Environment variables (gitignored)
├── .env.example                # Environment template
├── MyPyBot.db                    # SQLite database (gitignored)
├── FEATURES.md                 # Complete feature guide
├── IMPLEMENTATION_SUMMARY.md   # Development summary
└── env/                        # Virtual environment (gitignored)
```

## 🧪 Testing

The bot includes comprehensive error handling:
- Missing API keys show helpful setup instructions
- Failed API calls have graceful fallbacks
- AI parsing failures use sensible defaults
- All user inputs are validated

Test with:
```
"What can you do?"  # See all capabilities
"Give me my daily briefing"  # Test multiple features
```

## 🛠️ Development

### Adding New Features
1. Add detection function (e.g., `detect_xxx_request()`)
2. Add handler function (e.g., `handle_xxx()`)
3. Add to `handle_message()` dispatch
4. Update database schema if needed
5. Update help text

### Code Style
- Functions organized by feature category
- Extensive inline comments
- Natural language detection with regex
- AI-powered parsing for complex inputs

### Modular Skills
- Player services are defined through paired metadata.json + instructions.md files under `skills`.
- `services/plugin_registry.py` scans the folders, reads the markdown documentation, and instantiates the configured class so adding or swapping services is as simple as dropping new files.
- Consult `skills/README.md` for the exact schema and naming conventions when adding a new skill.

## 📊 Statistics

- **Total Features**: 18 core features
- **Database Tables**: 9 tables
- **Lines of Code**: 3900+ lines
- **API Integrations**: 5 (OpenWeather, NewsAPI, Wikipedia, DuckDuckGo, Gmail)
- **Detection Functions**: 15+ feature detectors
- **Natural Language**: Full conversation context support

## 🤝 Contributing

Contributions welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Open a Pull Request

### Release Process

This project builds release binaries automatically from Git tags.

```bash
git add -A
git commit -m "release: v0.0.2"
git tag v0.0.2
git push origin main
git push origin v0.0.2
```

After the workflow completes, check the GitHub **Releases** page for:
- `pybot-linux.tar.gz`
- `pybot-macos.tar.gz`
- `pybot-windows.zip`
- their corresponding `.sha256` checksum files

## 📜 License

MIT License - See LICENSE file for details

## 🙏 Acknowledgments

- OpenAI for GPT models
- Ollama for local AI
- Telegram for Bot API
- OpenWeatherMap, NewsAPI, Wikipedia for data APIs

## 📞 Support

For issues, questions, or feature requests:
- Open an issue on GitHub
- Check [FEATURES.md](FEATURES.md) for usage details
- Review [IMPLEMENTATION_SUMMARY.md](IMPLEMENTATION_SUMMARY.md) for technical details

---

Made with ❤️ by AI enthusiasts | Powered by Ollama & Python
