# config.py
# Configuration file for Ai Assistant AI Bot

import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Telegram Bot Token (get from @BotFather)
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")

# Discord Configuration
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN", "")
DISCORD_ALLOWED_CHANNEL_IDS = os.getenv("DISCORD_ALLOWED_CHANNEL_IDS", "")

# WhatsApp (Twilio) Configuration
WHATSAPP_TWILIO_ACCOUNT_SID = os.getenv("WHATSAPP_TWILIO_ACCOUNT_SID", "")
WHATSAPP_TWILIO_AUTH_TOKEN = os.getenv("WHATSAPP_TWILIO_AUTH_TOKEN", "")
WHATSAPP_TWILIO_NUMBER = os.getenv("WHATSAPP_TWILIO_NUMBER", "")
WHATSAPP_WEBHOOK_VERIFY_TOKEN = os.getenv("WHATSAPP_WEBHOOK_VERIFY_TOKEN", "")

# AI Backend: "ollama" or "openai"
AI_BACKEND = os.getenv("AI_BACKEND", "ollama")

# Ollama Configuration
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434/api/generate")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2")

# Performance Settings
CHAT_HISTORY_LIMIT = int(os.getenv("CHAT_HISTORY_LIMIT", "5"))  # Number of previous messages to remember

# Skill metadata auto-sync settings
raw_auto_sync_skill_metadata = os.getenv("AUTO_SYNC_SKILL_METADATA", "true").strip().lower()
AUTO_SYNC_SKILL_METADATA = raw_auto_sync_skill_metadata in ["1", "true", "yes", "on"]
raw_skill_metadata_sync_only_missing = os.getenv("SKILL_METADATA_SYNC_ONLY_MISSING", "false").strip().lower()
SKILL_METADATA_SYNC_ONLY_MISSING = raw_skill_metadata_sync_only_missing in ["1", "true", "yes", "on"]

# Universal NLU Configuration (semantic intent fallback)
raw_nlu_enabled = os.getenv("NLU_ENABLED", "true").strip().lower()
NLU_ENABLED = raw_nlu_enabled in ["1", "true", "yes", "on"]
NLU_MODEL = os.getenv("NLU_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
NLU_MIN_CONFIDENCE = float(os.getenv("NLU_MIN_CONFIDENCE", "0.22"))

# RAG Configuration
raw_rag_enabled = os.getenv("RAG_ENABLED", "true").strip().lower()
RAG_ENABLED = raw_rag_enabled in ["1", "true", "yes", "on"]
RAG_KB_DIR = os.getenv("RAG_KB_DIR", "knowledge")
RAG_CHUNK_SIZE = int(os.getenv("RAG_CHUNK_SIZE", "700"))
RAG_TOP_K = int(os.getenv("RAG_TOP_K", "3"))
RAG_MAX_CONTEXT_CHARS = int(os.getenv("RAG_MAX_CONTEXT_CHARS", "2000"))

# OpenAI Configuration (if using OpenAI backend)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-3.5-turbo")

# Gmail Configuration
GMAIL_EMAIL = os.getenv("GMAIL_EMAIL", "")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD", "")  # Get from Google Account Settings > Security > App passwords

# Cron Job Configuration
# Your Telegram user ID (for sending cron notifications)
CRON_NOTIFY_USER_ID = os.getenv("CRON_NOTIFY_USER_ID", "")  # Your Telegram user ID

# Weather Configuration
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY", "")
DEFAULT_CITY = os.getenv("DEFAULT_CITY", "London")
DEFAULT_COUNTRY_CODE = os.getenv("DEFAULT_COUNTRY_CODE", "GB")

# News Configuration
NEWSAPI_KEY = os.getenv("NEWSAPI_KEY", "")

# Trello Configuration
TRELLO_API_KEY = os.getenv("TRELLO_API_KEY", "")
TRELLO_TOKEN = os.getenv("TRELLO_TOKEN", "")

# Dashboard Security / Live Refresh
DASHBOARD_JWT_SECRET = os.getenv("DASHBOARD_JWT_SECRET", "")
DASHBOARD_JWT_ALGORITHM = os.getenv("DASHBOARD_JWT_ALGORITHM", "HS256")
DASHBOARD_JWT_EXPIRE_HOURS = int(os.getenv("DASHBOARD_JWT_EXPIRE_HOURS", "24"))
DASHBOARD_AUTO_REFRESH_SECONDS = int(os.getenv("DASHBOARD_AUTO_REFRESH_SECONDS", "3"))
