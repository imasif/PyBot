# bot.py
import argparse
import asyncio
import getpass
import html
import importlib
import json
import logging
import math
import os
import platform
import re
import shlex
import subprocess
import sys
import threading
import time
from collections import defaultdict
from datetime import datetime, timedelta

import advanced_features
import config
import database
import openai
import psutil

import requests
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from telegram import BotCommand, Update
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from plugin_registry import get_optional_config_keys, get_plugin_api_status, get_required_config_keys, get_skill, get_skill_definitions, invoke_first_available_method, invoke_service_method, sync_skill_metadata_commands
from services.nlu import UniversalNLUService

# Initialize database
database.init_db()

# Enable logging
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# Global scheduler and bot instance
scheduler = BackgroundScheduler()
bot_instance = None
discord_thread = None
nlu_service = UniversalNLUService()


def call_service(service_name, method_name, *args, default=None, **kwargs):
    return invoke_service_method(service_name, method_name, *args, default=default, **kwargs)

CORE_ALLOWED_CONFIG_KEYS = [
    'TELEGRAM_BOT_TOKEN', 'CRON_NOTIFY_USER_ID',
    'DISCORD_BOT_TOKEN', 'DISCORD_ALLOWED_CHANNEL_IDS',
    'WHATSAPP_TWILIO_ACCOUNT_SID', 'WHATSAPP_TWILIO_AUTH_TOKEN',
    'WHATSAPP_TWILIO_NUMBER', 'WHATSAPP_WEBHOOK_VERIFY_TOKEN',
    'AI_BACKEND', 'OLLAMA_URL', 'OLLAMA_MODEL',
    'CHAT_HISTORY_LIMIT',
    'AUTO_SYNC_SKILL_METADATA', 'SKILL_METADATA_SYNC_ONLY_MISSING',
    'NLU_ENABLED', 'NLU_MODEL', 'NLU_MIN_CONFIDENCE',
    'RAG_ENABLED', 'RAG_KB_DIR', 'RAG_CHUNK_SIZE', 'RAG_TOP_K', 'RAG_MAX_CONTEXT_CHARS',
    'OPENAI_API_KEY', 'OPENAI_MODEL',
    'DASHBOARD_JWT_SECRET', 'DASHBOARD_JWT_ALGORITHM',
    'DASHBOARD_JWT_EXPIRE_HOURS', 'DASHBOARD_AUTO_REFRESH_SECONDS',
]
NUMERIC_CONFIG_KEYS = {'CHAT_HISTORY_LIMIT', 'NLU_MIN_CONFIDENCE', 'RAG_TOP_K', 'RAG_CHUNK_SIZE', 'RAG_MAX_CONTEXT_CHARS', 'DASHBOARD_JWT_EXPIRE_HOURS', 'DASHBOARD_AUTO_REFRESH_SECONDS'}
BOOLEAN_CONFIG_KEYS = {'NLU_ENABLED', 'RAG_ENABLED', 'AUTO_SYNC_SKILL_METADATA', 'SKILL_METADATA_SYNC_ONLY_MISSING'}
FLOAT_CONFIG_KEYS = {'NLU_MIN_CONFIDENCE'}
SENSITIVE_CONFIG_KEYS = {
    'TELEGRAM_BOT_TOKEN', 'OPENAI_API_KEY', 'OPENWEATHER_API_KEY', 'NEWSAPI_KEY',
    'GMAIL_APP_PASSWORD', 'DISCORD_BOT_TOKEN', 'WHATSAPP_TWILIO_AUTH_TOKEN',
    'WHATSAPP_TWILIO_ACCOUNT_SID', 'TRELLO_API_KEY', 'TRELLO_TOKEN', 'DASHBOARD_JWT_SECRET'
}
REQUIRED_ONBOARD_KEYS = {'TELEGRAM_BOT_TOKEN', 'CRON_NOTIFY_USER_ID', 'AI_BACKEND'}


def get_runtime_allowed_config_keys():
    dynamic_keys = get_required_config_keys()
    optional_keys = get_optional_config_keys()

    merged = []
    seen = set()
    for key in [*CORE_ALLOWED_CONFIG_KEYS, *optional_keys, *dynamic_keys]:
        normalized = str(key).strip().upper()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        merged.append(normalized)
    return merged


def is_runtime_allowed_config_key(key):
    return str(key).strip().upper() in set(get_runtime_allowed_config_keys())


def _matches_skill_keywords(skill_slug: str, text: str) -> bool:
    candidate = (text or '').lower().strip()
    slug = (skill_slug or '').strip()
    if not candidate or not slug:
        return False

    skill = get_skill(slug)
    keywords = [str(item).lower().strip() for item in ((skill.keywords if skill else []) or []) if str(item).strip()]
    if not keywords:
        return False

    return any(keyword in candidate for keyword in keywords)


def _matched_skill_slugs(text: str):
    candidate = (text or '').lower().strip()
    if not candidate:
        return []

    matched = []
    for slug, skill in get_skill_definitions().items():
        if not getattr(skill, 'enabled', False):
            continue
        keywords = [str(item).lower().strip() for item in ((skill.keywords if skill else []) or []) if str(item).strip()]
        if keywords and any(keyword in candidate for keyword in keywords):
            matched.append(slug)
    return matched


def _matches_any_skill_keywords(text: str, excluded_slugs=None) -> bool:
    excluded = set(str(slug).strip().lower() for slug in (excluded_slugs or []) if str(slug).strip())
    for slug in _matched_skill_slugs(text):
        if slug.lower() not in excluded:
            return True
    return False


def _build_dynamic_capabilities_text() -> str:
    enabled_skills = [skill for skill in get_skill_definitions().values() if skill.enabled]
    enabled_skills.sort(key=lambda skill: (skill.name or skill.slug).lower())

    lines = [
        "I'm your personal AI assistant with these capabilities:",
        "",
        "💬 AI Chat:",
        "  • Talk naturally and I'll route your request to the right skill",
        "",
        "🧩 Enabled Skills:",
    ]

    if enabled_skills:
        for skill in enabled_skills:
            skill_name = skill.name or skill.slug.replace('_', ' ').title()
            description = (skill.description or "Available").strip()
            lines.append(f"  • {skill_name} — {description}")
    else:
        lines.append("  • No skills are currently enabled")

    lines.extend([
        "",
        "🛠️ Core Bot Features:",
        "  • Scheduling & reminders (/addjob, /listjobs, /removejob)",
        "  • Command execution (/run)",
        "  • Runtime config management (/config, /setconfig, /gateway)",
        "",
        "Use /start to see all commands.",
    ])
    return "\n".join(lines)


def _build_dynamic_start_help() -> str:
    bot_name = get_bot_name()
    enabled_skills = [skill for skill in get_skill_definitions().values() if skill.enabled]
    enabled_skills.sort(key=lambda skill: (skill.name or skill.slug).lower())

    lines = [
        f"Hi! I'm {bot_name}, your AI assistant.",
        "",
        "Enabled skills:",
    ]

    if enabled_skills:
        for skill in enabled_skills:
            skill_name = skill.name or skill.slug.replace('_', ' ').title()
            description = (skill.description or "Available").strip()
            lines.append(f"- {skill_name}: {description}")
    else:
        lines.append("- No skills currently enabled")

    lines.extend([
        "",
        "Core commands:",
        "- /status : bot health and runtime overview",
        "- /config : show current runtime config",
        "- /setconfig KEY VALUE : update config",
        "- /gateway list|get|set : gateway config operations",
        "- /addjob, /listjobs, /removejob : scheduling",
        "- /run <command> : execute shell command",
        "- /tools : advanced tool commands",
        "",
        "You can also talk naturally, for example:",
        "- check my messages",
        "- remind me everyday at 4:30 am",
        "- show my jobs",
    ])
    return "\n".join(lines)


def get_app_root():
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def get_env_path():
    return os.path.join(get_app_root(), '.env')


def get_env_example_path():
    return os.path.join(get_app_root(), '.env.example')


def is_placeholder_value(value):
    if not value:
        return True
    normalized = str(value).strip().lower()
    placeholder_tokens = [
        'your_', 'your-', '_here', 'change_me', 'changeme', 'example',
        'token_here', 'api_key_here', 'password_here'
    ]
    return any(token in normalized for token in placeholder_tokens)


def _read_env_values(env_path=None):
    path = env_path or get_env_path()
    values = {}
    if not os.path.exists(path):
        return values
    try:
        with open(path, 'r', encoding='utf-8') as env_file:
            for raw_line in env_file:
                line = raw_line.strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                key, value = line.split('=', 1)
                values[key.strip()] = value.strip()
    except Exception as exc:
        logger.error(f"Failed to read env file {path}: {exc}")
    return values


def _parse_env_example(example_path=None):
    path = example_path or get_env_example_path()
    entries = []
    if not os.path.exists(path):
        return entries

    try:
        with open(path, 'r', encoding='utf-8') as env_file:
            for raw_line in env_file:
                line = raw_line.strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                key, default = line.split('=', 1)
                entries.append((key.strip(), default.strip()))
    except Exception as exc:
        logger.error(f"Failed to parse .env.example: {exc}")
    return entries


def _sanitize_default(value):
    return '' if is_placeholder_value(value) else value


def _mask_value(key, value):
    if value is None or value == '':
        return ''
    if key in SENSITIVE_CONFIG_KEYS:
        if len(value) <= 6:
            return '*' * len(value)
        return f"{value[:3]}***{value[-3:]}"
    return value


def _reload_runtime_config():
    importlib.reload(config)


def _coerce_config_value(key, value):
    normalized_key = key.upper()
    if normalized_key in FLOAT_CONFIG_KEYS:
        return float(value)
    if normalized_key in NUMERIC_CONFIG_KEYS:
        return int(value)
    if normalized_key in BOOLEAN_CONFIG_KEYS:
        normalized = str(value).strip().lower()
        if normalized not in ['true', 'false', '1', '0', 'yes', 'no', 'on', 'off']:
            raise ValueError(f"Invalid boolean value for {normalized_key}")
        return normalized in ['true', '1', 'yes', 'on']
    if normalized_key == 'AI_BACKEND':
        backend = str(value).strip().lower()
        if backend not in ['ollama', 'openai']:
            raise ValueError("AI_BACKEND must be 'ollama' or 'openai'")
        return backend
    return value


def apply_config_update(key, value, persist=True):
    normalized_key = key.upper().strip()
    if not is_runtime_allowed_config_key(normalized_key):
        raise KeyError(normalized_key)

    typed_value = _coerce_config_value(normalized_key, value)
    setattr(config, normalized_key, typed_value)
    if persist:
        update_env_file(normalized_key, str(value), env_path=get_env_path())
    return typed_value


def get_missing_onboarding_keys():
    missing = []
    for key in ['TELEGRAM_BOT_TOKEN', 'CRON_NOTIFY_USER_ID']:
        value = getattr(config, key, '')
        if is_placeholder_value(value):
            missing.append(key)

    backend = str(getattr(config, 'AI_BACKEND', 'ollama')).strip().lower()
    if backend == 'openai' and is_placeholder_value(getattr(config, 'OPENAI_API_KEY', '')):
        missing.append('OPENAI_API_KEY')

    return missing


def get_onboarding_script_path():
    root = get_app_root()
    primary = os.path.join(root, 'scripts', 'onboarding.sh')
    fallback = os.path.join(root, 'scripts', 'setup_env.sh')
    if os.path.exists(primary):
        return primary
    if os.path.exists(fallback):
        return fallback
    return None


def run_onboarding_script():
    script_path = get_onboarding_script_path()
    if not script_path:
        print("❌ Onboarding script not found. Expected scripts/onboarding.sh")
        return False

    print(f"🚀 Running onboarding script: {script_path}")
    try:
        subprocess.run(['bash', script_path], check=True)
        _reload_runtime_config()
        missing = get_missing_onboarding_keys()
        if missing:
            print(f"❌ Onboarding incomplete. Missing: {', '.join(missing)}")
            return False
        return True
    except subprocess.CalledProcessError as exc:
        print(f"❌ Onboarding script failed: {exc}")
        return False


def ensure_runtime_onboarding():
    missing = get_missing_onboarding_keys()
    if not missing:
        return True

    script_path = get_onboarding_script_path()
    if not sys.stdin.isatty():
        if script_path:
            logger.error(f"Missing required config: {missing}. Run 'bash {script_path}' or './pybot onboard' in interactive shell.")
        else:
            logger.error(f"Missing required config: {missing}. Run './pybot onboard' in interactive shell.")
        return False

    print(f"Missing required config: {', '.join(missing)}")
    return run_onboarding_script()


def run_gateway_cli(args):
    action = args.gateway_action
    if action == 'list':
        for key in get_runtime_allowed_config_keys():
            print(f"{key}={_mask_value(key, str(getattr(config, key, '')))}")
        return 0

    if action == 'doctor':
        missing = get_missing_onboarding_keys()
        if missing:
            print(f"❌ Missing required config: {', '.join(missing)}")
            return 1
        print("✅ Required onboarding config looks good.")
        return 0

    key = (args.key or '').upper()
    if not is_runtime_allowed_config_key(key):
        print(f"❌ Invalid config key: {key}")
        return 1

    if action == 'get':
        value = str(getattr(config, key, ''))
        print(f"{key}={_mask_value(key, value)}")
        return 0

    if action == 'set':
        try:
            typed_value = apply_config_update(key, args.value)
            if key in ['DISCORD_BOT_TOKEN', 'DISCORD_ALLOWED_CHANNEL_IDS']:
                ensure_discord_bridge_running()
            print(f"✅ Updated {key}={_mask_value(key, str(typed_value))}")
            return 0
        except Exception as exc:
            print(f"❌ Failed to update config: {exc}")
            return 1

    print("❌ Unknown gateway action")
    return 1


def handle_cli_entrypoint():
    parser = argparse.ArgumentParser(description='PyBot runtime and configuration manager')
    subparsers = parser.add_subparsers(dest='command')

    subparsers.add_parser('onboard', help='Run first-time onboarding wizard')

    gateway_parser = subparsers.add_parser('gateway', help='Manage configuration from command line')
    gateway_subparsers = gateway_parser.add_subparsers(dest='gateway_action', required=True)
    gateway_subparsers.add_parser('list', help='List supported config keys and current values')
    gateway_subparsers.add_parser('doctor', help='Validate required onboarding config')

    get_parser = gateway_subparsers.add_parser('get', help='Get a single config value')
    get_parser.add_argument('key', help='Config key')

    set_parser = gateway_subparsers.add_parser('set', help='Set a single config value')
    set_parser.add_argument('key', help='Config key')
    set_parser.add_argument('value', help='Config value')

    args = parser.parse_args()
    if not args.command:
        return None

    if args.command == 'onboard':
        return 0 if run_onboarding_script() else 1

    if args.command == 'gateway':
        return run_gateway_cli(args)

    return 0

# Cache for identity to avoid reading file on every request
_identity_cache = None
_identity_mtime = 0

# Cache for lightweight local RAG index
_rag_cache = {
    "signature": None,
    "chunks": [],
}


def _rag_tokenize(text):
    return re.findall(r"[a-zA-Z0-9_]+", (text or "").lower())


def _rag_chunk_text(text, chunk_size=700):
    cleaned = (text or "").strip()
    if not cleaned:
        return []
    return [cleaned[i:i + chunk_size] for i in range(0, len(cleaned), chunk_size)]


def _build_rag_index():
    rag_enabled = str(getattr(config, 'RAG_ENABLED', 'true')).lower() in ['1', 'true', 'yes', 'on']
    if not rag_enabled:
        return []

    kb_dir = getattr(config, 'RAG_KB_DIR', 'knowledge')
    chunk_size = int(getattr(config, 'RAG_CHUNK_SIZE', 700))
    allowed_ext = {'.md', '.txt', '.rst', '.json', '.py'}

    if not os.path.isdir(kb_dir):
        return []

    file_paths = []
    for root, _, files in os.walk(kb_dir):
        for name in files:
            ext = os.path.splitext(name)[1].lower()
            if ext in allowed_ext:
                file_paths.append(os.path.join(root, name))

    signature = []
    for path in sorted(file_paths):
        try:
            stat = os.stat(path)
            signature.append((path, stat.st_mtime, stat.st_size))
        except OSError:
            continue

    signature = tuple(signature)
    if _rag_cache.get("signature") == signature:
        return _rag_cache.get("chunks", [])

    chunks = []
    for path in sorted(file_paths):
        try:
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
        except Exception:
            continue

        for part in _rag_chunk_text(content, chunk_size=chunk_size):
            tokens = _rag_tokenize(part)
            if not tokens:
                continue
            chunks.append({
                'source': path,
                'text': part,
                'tokens': tokens,
            })

    _rag_cache['signature'] = signature
    _rag_cache['chunks'] = chunks
    logger.info(f"RAG index rebuilt: {len(chunks)} chunks from {len(file_paths)} files")
    return chunks


def get_rag_context(query, top_k=None):
    chunks = _build_rag_index()
    if not chunks:
        return None

    q_tokens = _rag_tokenize(query)
    if not q_tokens:
        return None

    q_set = set(q_tokens)
    scored = []
    for chunk in chunks:
        token_set = set(chunk['tokens'])
        overlap = q_set.intersection(token_set)
        if not overlap:
            continue
        score = sum(chunk['tokens'].count(tok) for tok in overlap) / math.log(len(chunk['tokens']) + 10)
        scored.append((score, chunk))

    if not scored:
        return None

    k = int(top_k or getattr(config, 'RAG_TOP_K', 3))
    top_chunks = [item[1] for item in sorted(scored, key=lambda x: x[0], reverse=True)[:k]]

    max_chars = int(getattr(config, 'RAG_MAX_CONTEXT_CHARS', 2000))
    context_parts = []
    used = 0
    for item in top_chunks:
        snippet = f"Source: {item['source']}\n{item['text']}"
        if used + len(snippet) > max_chars:
            remaining = max_chars - used
            if remaining <= 120:
                break
            snippet = snippet[:remaining]
        context_parts.append(snippet)
        used += len(snippet)
        if used >= max_chars:
            break

    if not context_parts:
        return None

    return "\n\n---\n\n".join(context_parts)


def inject_rag_context(user_prompt):
    rag_context = get_rag_context(user_prompt)
    if not rag_context:
        return user_prompt

    return (
        "Use the following retrieved context when relevant. "
        "If it is not relevant, ignore it. Do not invent facts.\n\n"
        f"Retrieved context:\n{rag_context}\n\n"
        f"User request: {user_prompt}"
    )

# ---------- AI Functions (unchanged) ----------
def read_identity():
    """Read bot identity from identity.md with caching"""
    global _identity_cache, _identity_mtime
    try:
        current_mtime = os.path.getmtime('identity.md')
        # Only reload if file changed
        if _identity_cache is None or current_mtime != _identity_mtime:
            with open('identity.md', 'r') as f:
                _identity_cache = f.read()
            _identity_mtime = current_mtime
        return _identity_cache
    except FileNotFoundError:
        return "You are a helpful AI assistant."
    except Exception as e:
        logger.error(f"Error reading identity: {e}")
        return _identity_cache if _identity_cache else "You are a helpful AI assistant."

def get_bot_name():
    """Extract bot name from identity.md"""
    try:
        identity = read_identity()
        # Look for the name under ## Name heading
        match = re.search(r'##\s*Name\s*\n\s*(.+)', identity)
        if match:
            return match.group(1).strip()
        return "MyPyBot"  # Default fallback
    except Exception as e:
        logger.error(f"Error extracting bot name: {e}")
        return "MyPyBot"

def update_identity(new_content):
    """Update bot identity file"""
    try:
        if new_content:
            current_time_text = datetime.now().strftime("%A, %B %d, %Y, %H:%M")
            new_content = re.sub(
                r'(Current date and time\s*:\s*)([^\n\r]+)',
                rf'\1{current_time_text}',
                new_content,
                flags=re.IGNORECASE,
            )
        with open('identity.md', 'w') as f:
            f.write(new_content)
        return True
    except Exception as e:
        logger.error(f"Identity update error: {e}")
        return False

def ask_ollama(prompt: str, chat_history=None) -> str:
    # Read bot identity (cached)
    identity = read_identity()
    
    # Add current time/date context in natural language
    now = datetime.now()
    hour = now.hour
    minute = now.minute
    day_name = now.strftime("%A")
    month = now.strftime("%B")
    day = now.day
    year = now.year
    
    # Build natural time context (no rigid formatting)
    time_context = f"\n\nNote: Current time is {hour} hours and {minute} minutes (24h format). Today is {day_name}, {month} {day}, {year}."
    response_style = (
        "\n\nResponse style rules:"
        "\n- Do NOT add any title or heading like 'X Response' or markdown headings."
        "\n- Start directly with the answer."
        "\n- Keep replies concise and conversational unless user asks for details."
    )
    
    # Build context - simplified for speed
    if chat_history and len(chat_history) > 0:
        # Only include last few messages to keep context small
        recent = chat_history[-3:]  # Just last 3 exchanges
        context = f"{identity}{time_context}{response_style}\n\nRecent conversation:\n"
        for msg, reply in recent:
            context += f"User: {msg}\nAssistant: {reply}\n"
        context += f"\nUser: {prompt}\nAssistant:"
        full_prompt = context
    else:
        # Just identity + prompt
        full_prompt = f"{identity}{time_context}{response_style}\n\nUser: {prompt}\nAssistant:"
    
    payload = {
        "model": config.OLLAMA_MODEL,
        "prompt": full_prompt,
        "stream": False
    }
    try:
        response = requests.post(config.OLLAMA_URL, json=payload)
        response.raise_for_status()
        return response.json()["response"]
    except Exception as e:
        logger.error(f"Ollama error: {e}")
        return "Sorry, I'm having trouble connecting to my brain."

def ask_openai(prompt: str) -> str:
    openai.api_key = config.OPENAI_API_KEY
    try:
        completion = openai.ChatCompletion.create(
            model=config.OPENAI_MODEL,
            messages=[{"role": "user", "content": prompt}]
        )
        return completion.choices[0].message.content
    except Exception as e:
        logger.error(f"OpenAI error: {e}")
        return "Sorry, I'm having trouble with OpenAI."

def get_ai_response(prompt: str, user_id=None, use_rag=False) -> str:
    if use_rag:
        prompt = inject_rag_context(prompt)

    # Get recent chat history for context (configurable for speed vs memory tradeoff)
    chat_history = None
    if user_id:
        limit = getattr(config, 'CHAT_HISTORY_LIMIT', 5)
        chat_history = database.get_user_chat_history(user_id, limit=limit)
    
    if config.AI_BACKEND == "ollama":
        return ask_ollama(prompt, chat_history)
    elif config.AI_BACKEND == "openai":
        return ask_openai(prompt)
    else:
        return "Unknown AI backend."

# ---------- Cron Job Functions ----------
def send_telegram_message(user_id, message, parse_mode=ParseMode.MARKDOWN):
    """Send a message to a Telegram user"""
    if bot_instance:
        try:
            asyncio.run(bot_instance.bot.send_message(chat_id=user_id, text=message, parse_mode=ParseMode.MARKDOWN if parse_mode is None else parse_mode))
        except Exception as e:
            logger.error(f"Error sending message: {e}")

def execute_cron_job(job_type, params):
    """Execute a cron job based on its type"""
    call_service(
        'cron',
        'execute_cron_job',
        job_type,
        params,
        notify_user_id=config.CRON_NOTIFY_USER_ID,
        send_message=send_telegram_message,
        fetch_scheduled_check_result=lambda target_user_id: invoke_first_available_method(
            'handle_command_action',
            'unread',
            [],
            str(target_user_id),
            default="This service is not available right now. Restart the bot so it can initialize.",
        ),
        generate_sleep_report=generate_sleep_report,
        generate_tracking_report=generate_tracking_report,
    )

def run_custom_command(command, timeout=30):
    """Execute a custom shell command and return the output"""
    return call_service(
        'cron',
        'run_custom_command',
        command,
        timeout=timeout,
        default="❌ Cron service is not available right now.",
    )

# ---------- Browser Automation Functions ----------
def automate_browser(action_type, **kwargs):
    """Automate browser actions using Selenium"""
    return call_service(
        'browser',
        'automate',
        action_type,
        default="❌ Browser service is not available right now.",
        **kwargs,
    )

def auto_resolve_common_queries(text):
    """Auto-resolve common system queries with immediate command execution"""
    
    text_lower = text.lower().strip()
    os_name = platform.system()
    
    # Pattern matching for common queries that should auto-execute
    auto_patterns = {
        # Time and Date queries - COMMENTED OUT to let LLM handle naturally
        # r'(?:what(?:\'s| is) (?:the )?)?current (?:time|date)': 'date' if os_name != 'Windows' else 'echo %TIME% %DATE%',
        # r'(?:what(?:\'s| is) (?:the )?)?time(?: now| is it)?': 'date +"%H:%M:%S"' if os_name != 'Windows' else 'echo %TIME%',
        # r'(?:what(?:\'s| is) (?:the )?)?(?:today(?:\'s)?|date)(?: today)?': 'date +"%Y-%m-%d"' if os_name != 'Windows' else 'echo %DATE%',
        
        # User and system info
        r'(?:what(?:\'s| is) )?(?:my )?username': 'whoami' if os_name != 'Windows' else 'echo %USERNAME%',
        r'who am i': 'whoami',
        r'(?:what(?:\'s| is) )?(?:my )?current (?:directory|folder|path)': 'pwd' if os_name != 'Windows' else 'cd',
        r'where am i': 'pwd' if os_name != 'Windows' else 'cd',
        
        # System status
        r'(?:system )?uptime': 'uptime' if os_name != 'Windows' else 'systeminfo | find "System Boot Time"',
        r'(?:disk|storage) space': 'df -h' if os_name != 'Windows' else 'wmic logicaldisk get size,freespace,caption',
        r'(?:how much )?(?:free )?(?:disk|storage)(?: space)?': 'df -h /' if os_name != 'Windows' else 'wmic logicaldisk get freespace,caption',
        r'memory usage': 'free -h' if os_name != 'Windows' else 'systeminfo | find "Available Physical Memory"',
        r'(?:cpu|processor) info': 'lscpu | head -20' if os_name != 'Windows' else 'wmic cpu get name',
        
        # Network info
        r'(?:my )?ip address': 'hostname -I' if os_name != 'Windows' else 'ipconfig | find "IPv4"',
        r'network (?:info|status)': 'ip addr show' if os_name != 'Windows' else 'ipconfig',
        
        # File operations (safe ones)
        r'list (?:files|directories)': 'ls -lh' if os_name != 'Windows' else 'dir',
        r'show (?:files|directories)': 'ls -la' if os_name != 'Windows' else 'dir',
    }
    
    for pattern, command in auto_patterns.items():
        if re.search(pattern, text_lower):
            return {
                "is_command_request": True,
                "command": command,
                "explanation": f"Getting {pattern}",
                "confidence": "high",
                "auto_resolved": True
            }
    
    return None

# ---------- Reminders Functions ----------
# NOTE: Reminders are now merged into cron jobs system
# One-time reminders are created as cron jobs with specific datetime and run_once=True

# ---------- Shopping List Functions ----------
def detect_shopping_request(text, user_id=None):
    """Detect shopping list requests"""
    return call_service(
        'shopping',
        'detect_request',
        text,
        user_id=user_id,
        check_learned_patterns=check_learned_patterns,
        learn_from_interaction=learn_from_interaction,
        default=None,
    )

def handle_shopping_add(items_text, user_id):
    """Add items to shopping list"""
    return call_service('shopping', 'add_items', items_text, user_id, default="❌ Shopping service is not available right now.")

def handle_shopping_list(user_id):
    """Show shopping list"""
    return call_service('shopping', 'list_items', user_id, default="❌ Shopping service is not available right now.")

def handle_shopping_clear(user_id):
    """Clear purchased items from shopping list"""
    return call_service('shopping', 'clear_items', user_id, default="❌ Shopping service is not available right now.")

# ---------- Timer Functions ----------
def detect_timer_request(text, user_id=None):
    """Detect timer requests"""
    return call_service(
        'timer',
        'detect_request',
        text,
        user_id=user_id,
        check_learned_patterns=check_learned_patterns,
        learn_from_interaction=learn_from_interaction,
        default=None,
    )

def handle_timer_create(duration_text, user_id):
    """Create a timer"""
    return call_service('timer', 'create_timer', duration_text, user_id, default="❌ Timer service is not available right now.")

def handle_timer_list(user_id):
    """List active timers"""
    return call_service('timer', 'list_timers', user_id, default="❌ Timer service is not available right now.")

# ---------- Web Search Functions ----------
def detect_search_request(text, user_id=None):
    """Detect if user wants to search the web"""
    return call_service(
        'info_search',
        'detect_search_request',
        text,
        user_id=user_id,
        check_learned_patterns=check_learned_patterns,
        learn_from_interaction=learn_from_interaction,
        default=None,
    )

def search_web(query):
    """Search the web using DuckDuckGo"""
    return call_service('info_search', 'search_web', query, default="❌ Search service is not available right now.")

# ---------- Wikipedia Functions ----------
def detect_wikipedia_request(text, user_id=None):
    """Detect if user wants Wikipedia information"""
    return call_service(
        'info_search',
        'detect_wikipedia_request',
        text,
        user_id=user_id,
        check_learned_patterns=check_learned_patterns,
        learn_from_interaction=learn_from_interaction,
        default=None,
    )

def search_wikipedia(query):
    """Search Wikipedia for information"""
    return call_service('info_search', 'search_wikipedia', query, default="❌ Search service is not available right now.")

# ---------- Unit Conversion & Calculator Functions ----------
def detect_calculation_request(text):
    """Detect math calculations and unit conversions"""
    return call_service('calculation', 'detect_request', text, default=False)

def handle_calculation(expression):
    """Handle calculations and unit conversions using AI"""
    return call_service(
        'calculation',
        'handle',
        expression,
        ask_ollama,
        default="❌ Calculation service is not available right now.",
    )

# ---------- News Functions ----------
def detect_news_request(text, user_id=None):
    """Detect if user wants news"""
    return call_service(
        'news',
        'detect_request',
        text,
        user_id=user_id,
        check_learned_patterns=check_learned_patterns,
        learn_from_interaction=learn_from_interaction,
        default=None,
    )

def get_news(topic=None, limit=5):
    """Get news headlines using NewsAPI"""
    return call_service(
        'news',
        'get_news',
        config.NEWSAPI_KEY,
        topic=topic,
        limit=limit,
        default="❌ News service is not available right now.",
    )

def build_learned_entries(rows):
    entries = []
    for row in rows:
        pattern_id, pattern_type, user_input, detected_intent, confidence, success_count = row
        entries.append({
            'id': pattern_id,
            'pattern_type': pattern_type or 'general',
            'user_input': user_input,
            'detected_intent': detected_intent,
            'confidence': confidence,
            'success_count': success_count,
        })
    entries.sort(key=lambda e: (e['pattern_type'], -e['success_count'], -e['confidence']))
    return entries

LEARNED_DISPLAY_LIMIT = 5

def build_display_learned_entries(entries, per_type_limit=LEARNED_DISPLAY_LIMIT):
    grouped = defaultdict(list)
    for entry in entries:
        grouped[entry['pattern_type']].append(entry)

    ordered_types = sorted(grouped)
    display_entries = []
    for pattern_type in ordered_types:
        display_entries.extend(grouped[pattern_type][:per_type_limit])

    return ordered_types, grouped, display_entries

# ---------- AI Learning & Pattern Matching ----------
def check_learned_patterns(user_id, user_message, pattern_type):
    """Check if we've learned this pattern before"""
    
    
    learned = database.get_learned_patterns(user_id, pattern_type, min_confidence=0.6)
    
    for pattern_data in learned:
        _, _, user_input, detected_intent, confidence, success_count = pattern_data
        
        # Check if user message matches learned pattern (fuzzy match)
        if user_input in user_message.lower() or user_message.lower() in user_input:
            # Found a learned pattern!
            logger.info(f"🧠 Learned pattern matched: '{user_input}' → {detected_intent} (confidence: {confidence}, used: {success_count} times)")
            return detected_intent
    
    return None

def learn_from_interaction(user_id, user_message, pattern_type, detected_intent):
    """Save successful interaction for future learning"""
    try:
        database.save_learned_pattern(user_id, pattern_type, user_message, detected_intent)
        feedback = f"📚 Learned new pattern: {pattern_type} → {detected_intent}"
        logger.info(feedback)

        # Notify Telegram users inline when learning happens during a live chat loop.
        # Guard against non-Telegram IDs (e.g., long Discord snowflakes) to avoid noisy failures.
        if bot_instance and str(user_id).isdigit() and len(str(user_id)) <= 12:
            try:
                if hasattr(bot_instance, "create_task"):
                    bot_instance.create_task(bot_instance.bot.send_message(chat_id=int(user_id), text=feedback))
            except RuntimeError as exc:
                logger.debug(f"Skipping learning feedback due to runtime state: {exc}")
            except Exception as exc:
                logger.debug(f"Skipping learning feedback due to send error: {exc}")
    except Exception as e:
        logger.error(f"Learning error: {e}")


def is_successful_interaction_result(result_text):
    """Check whether a result text looks successful enough to learn from."""
    if result_text is None:
        return False

    text = str(result_text).strip().lower()
    if not text:
        return False

    failure_markers = [
        "❌",
        "error",
        "failed",
        "not found",
        "no such file or directory",
        "permission denied",
        "access denied",
        "unknown",
    ]
    return not any(marker in text for marker in failure_markers)


def learn_command_like_success(user_id, user_message, learned_intent, result_text=None):
    """Learn successful command-like interactions for future command interpretation."""
    if not user_id or not learned_intent:
        return

    normalized_message = (user_message or "").lower().strip()
    if _matches_any_skill_keywords(normalized_message):
        return

    if result_text is not None and not is_successful_interaction_result(result_text):
        return

    learn_from_interaction(user_id, normalized_message, 'command_like', learned_intent)

def get_personalized_greeting(user_id):
    """Get personalized greeting based on user context"""
    
    hour = datetime.now().hour
    
    # Check user's preferred greeting style
    greeting_style = database.get_user_context(user_id, 'greeting_style')
    
    if greeting_style == 'formal':
        return "Good day" if hour < 17 else "Good evening"
    elif greeting_style == 'casual':
        return "Hey" if hour < 12 else "Yo"
    else:
        # Default time-based
        if hour < 12:
            return "Good morning"
        elif hour < 17:
            return "Good afternoon"
        else:
            return "Good evening"

# ---------- Daily Briefing ----------
def detect_briefing_request(text, user_id=None):
    """Detect if user wants a daily briefing"""
    
    text_lower = text.lower().strip()
    
    # 📚 Check learned patterns first
    if user_id:
        learned = check_learned_patterns(user_id, text_lower, 'briefing')
        if learned:
            return {'action': 'briefing'}
    
    briefing_patterns = [
        r'(?:give me|show me|tell me)(?: my)? (?:daily |morning )?briefing',
        r'(?:what\'s|what is) (?:my )?(?:daily |morning )?(?:briefing|update)',
        r'(?:morning|daily) (?:briefing|update|summary)',
        r'brief me',
    ]
    
    for pattern in briefing_patterns:
        if re.search(pattern, text_lower):
            result = {'action': 'briefing'}
            # 📚 Learn this pattern
            if user_id:
                learn_from_interaction(user_id, text_lower, 'briefing', 'briefing')
            return result
    
    return None

def detect_status_request(text, user_id=None):
    """Detect if user wants bot status"""
    
    text_lower = text.lower().strip()
    
    # 📚 Check learned patterns first
    if user_id:
        learned = check_learned_patterns(user_id, text_lower, 'status')
        if learned:
            return {'action': 'status'}
    
    status_patterns = [
        r'(?:show|give|tell)(?: me)? (?:your |the |bot )?status',
        r'(?:what\'s|what is) (?:your |the |bot )?(?:status|health)',
        r'(?:are you (?:working|running|ok|operational|alive))',
        r'bot (?:status|health|info|information)',
        r'system (?:status|info)',
        r'check status',
    ]
    
    for pattern in status_patterns:
        if re.search(pattern, text_lower):
            result = {'action': 'status'}
            # 📚 Learn this pattern
            if user_id:
                learn_from_interaction(user_id, text_lower, 'status', 'status')
            return result
    
    return None

def generate_daily_briefing(user_id):
    """Generate a comprehensive daily briefing"""
    
    
    current_time = datetime.now().strftime('%I:%M %p')
    current_date = datetime.now().strftime('%A, %B %d, %Y')
    briefing = f"📋 **Daily Briefing - {current_date}**\n🕐 The time is {current_time}\n\n"

    briefing += invoke_first_available_method(
        'get_daily_briefing_section',
        default='',
    )
    
    # Upcoming scheduled tasks
    jobs = database.get_all_cron_jobs()
    enabled_jobs = [j for j in jobs if j['enabled']]
    if enabled_jobs:
        briefing += "⏰ **Today's Scheduled Tasks:**\n"
        for job in enabled_jobs[:5]:  # Limit to 5 tasks
            briefing += f"• {job['name']} ({job['schedule']})\n"
        briefing += "\n"
    
    # News headlines
    briefing += "📰 **Top News:**\n"
    news_result = get_news(limit=3)
    if "❌" not in news_result:
        # Extract headlines only
        
        headlines = re.findall(r'\*\*\d+\. (.+?)\*\*', news_result)
        for headline in headlines:
            briefing += f"• {headline}\n"
        briefing += "\n"
    else:
        briefing += "News unavailable\n\n"
    
    briefing += "_Have a great day! 🌟_"
    
    return briefing

def interpret_command_request(text, user_id=None):
    """Use AI to interpret a natural language request and suggest a shell command"""
    os_name = platform.system()  # Linux, Windows, Darwin (macOS)
    
    # First, check if this is a common query that can be auto-resolved
    auto_result = auto_resolve_common_queries(text)
    if auto_result:
        return auto_result
    
    # OS-specific command examples
    if os_name == "Windows":
        browser_cmd = "start chrome"
        url_open_cmd = "start"
    else:  # Linux, macOS
        browser_cmd = "google-chrome || chromium-browser || firefox"
        url_open_cmd = "xdg-open"
    
    prompt = f"""Interpret this user request and determine if they want to execute a shell command.

IMPORTANT: System OS is {os_name}. Provide {os_name}-compatible commands only!

User request: "{text}"

Return ONLY a JSON object:
{{
  "is_command_request": true/false,
  "command": "the shell command to execute",
  "explanation": "brief explanation of what the command does",
  "confidence": "high/medium/low"
}}

Examples for {os_name}:
- "show me files in this directory" → {{"is_command_request": true, "command": "ls -la", "explanation": "List all files with details", "confidence": "high"}}
- "what's my current directory?" → {{"is_command_request": true, "command": "pwd", "explanation": "Print working directory", "confidence": "high"}}
- "how much disk space?" → {{"is_command_request": true, "command": "df -h", "explanation": "Show disk space in human-readable format", "confidence": "high"}}
- "show running processes" → {{"is_command_request": true, "command": "ps aux", "explanation": "List all running processes", "confidence": "high"}}
- "open chrome" → {{"is_command_request": true, "command": "{browser_cmd}", "explanation": "Open Chrome browser", "confidence": "high"}}
- "play love song on youtube" → {{"is_command_request": true, "command": "{url_open_cmd} 'https://www.youtube.com/results?search_query=love+song'", "explanation": "Search and play on YouTube", "confidence": "high"}}
- "search youtube for tutorial" → {{"is_command_request": true, "command": "{url_open_cmd} 'https://www.youtube.com/results?search_query=tutorial'", "explanation": "Search YouTube", "confidence": "high"}}
- "open google.com" → {{"is_command_request": true, "command": "{url_open_cmd} 'https://google.com'", "explanation": "Open Google", "confidence": "high"}}
- "what time is it?" → {{"is_command_request": false}}
- "what's the date?" → {{"is_command_request": false}}
- "current time" → {{"is_command_request": false}}
- "check system uptime" → {{"is_command_request": true, "command": "uptime", "explanation": "Show system uptime and load", "confidence": "high"}}
- "hi" → {{"is_command_request": false}}
- "hello" → {{"is_command_request": false}}
- "thanks" → {{"is_command_request": false}}
- "how are you?" → {{"is_command_request": false}}

IMPORTANT: Do NOT interpret greetings, casual conversation, or questions as commands!
Only return true if the user is explicitly asking to RUN or EXECUTE something.

IMPORTANT for YouTube/web requests:
- Convert search terms to URL format (spaces to +)
- Use {url_open_cmd} to open URLs
- Format: {url_open_cmd} 'https://www.youtube.com/results?search_query=YOUR+SEARCH'
- Always wrap URLs in single quotes

Only return the JSON, nothing else."""

    # Pre-process common patterns for speed and reliability
    text_lower = text.lower().strip()

    # Do not treat email-skill intents as shell commands unless user explicitly asks to run a command.
    explicit_command_terms = ["run", "execute", "shell", "terminal", "command", "bash", "zsh", "cmd", "powershell"]
    if _matches_any_skill_keywords(text_lower) and not any(term in text_lower for term in explicit_command_terms):
        return {"is_command_request": False}

    # Use learned command-like mappings first
    if user_id:
        learned_intent = check_learned_patterns(user_id, text_lower, 'command_like')
        if learned_intent:
            if learned_intent.startswith('command_exec:'):
                learned_command = learned_intent.replace('command_exec:', '', 1)
                return {
                    "is_command_request": True,
                    "command": learned_command,
                    "explanation": f"Using learned command mapping: {learned_command}",
                    "confidence": "high"
                }
    
    # Immediately return False for common conversational phrases
    # These should NEVER be interpreted as commands
    conversational_phrases = [
        r'^hi$', r'^hello$', r'^hey$', r'^yo$', r'^sup$',
        r'^thanks?$', r'^thank you$', r'^thx$',
        r'^ok$', r'^okay$', r'^cool$', r'^nice$', r'^good$', r'^great$',
        r'^bye$', r'^goodbye$', r'^see you$',
        r'^yes$', r'^yeah$', r'^yep$', r'^no$', r'^nope$',
        r'^how are you', r'^what\'?s up', r'^how\'?s it going',
        r'^good morning', r'^good afternoon', r'^good evening', r'^good night',
        # Time and date queries - let LLM handle these naturally
        r'what.*time', r'time.*\?', r'current time', r'tell.*time',
        r'what.*date', r'date.*\?', r'today.*date', r'current date',
        r'^\w{1,3}$',  # Very short words (1-3 chars) are likely not commands
    ]
    
    for phrase_pattern in conversational_phrases:
        if re.match(phrase_pattern, text_lower):
            return {"is_command_request": False}
    
    # DuckDuckGo search patterns (explicit)
    ddg_patterns = [
        r'^(?:search(?:\s+using)?\s+(?:duck\s*duck\s*go|duckduckgo)\s*:?\s*)(.+)$',
        r'^(?:duck\s*duck\s*go|duckduckgo)\s*:?\s*(.+)$',
        r'^search\s+for\s+(.+?)\s+(?:on|using)\s+(?:duck\s*duck\s*go|duckduckgo)$',
    ]

    for pattern in ddg_patterns:
        match = re.search(pattern, text_lower, re.IGNORECASE)
        if match:
            search_query = match.group(1).strip()
            search_query = re.sub(r'\b(please|pls|plz)\b', '', search_query).strip(' :,-')
            if len(search_query) < 2:
                continue
            return {
                "is_command_request": True,
                "command": "BROWSER_AUTOMATION",
                "action": "web_search",
                "params": {"query": search_query, "engine": "duckduckgo"},
                "explanation": f"Searching DuckDuckGo for '{search_query}'",
                "confidence": "high"
            }

    # YouTube playback patterns (must explicitly mention YouTube)
    youtube_patterns = [
        r'^(?:open\s+)?youtube\s+(?:and\s+)?(?:play|search|find|watch)\s+(?:for\s+)?(.+)$',
        r'^(?:play|watch)\s+(.+?)\s+(?:on|in)\s+youtube$',
        r'^(?:search|find)\s+youtube\s+(?:for\s+)?(.+)$',
        r'^open\s+youtube\s+(?:and\s+)?(?:play|search|find|watch)\s+(.+)$',
    ]
    
    for pattern in youtube_patterns:
        match = re.search(pattern, text_lower, re.IGNORECASE)
        if match:
            search_query = match.group(1).strip()
            # Clean up common words
            search_query = re.sub(r'\b(please|pls|plz)\b', '', search_query).strip()
            
            return {
                "is_command_request": True,
                "command": "BROWSER_AUTOMATION",
                "action": "youtube_play",
                "params": {"query": search_query},
                "explanation": f"Playing '{search_query}' on YouTube with browser automation",
                "confidence": "high"
            }
    
    # Google search patterns (must explicitly mention search/google)
    google_search_patterns = [
        r'^(?:google|search for)\s+(.+)',
        r'^search\s+(.+?)\s+(?:on|in)\s+google',
        r'^look up\s+(.+?)\s+(?:on\s+)?google',
    ]
    
    for pattern in google_search_patterns:
        match = re.search(pattern, text_lower, re.IGNORECASE)
        if match:
            search_query = match.group(1).strip()
            search_query = re.sub(r'\b(please|pls|plz)\b', '', search_query).strip()
            
            # Skip conversational queries
            if len(search_query) < 3:
                continue
            if search_query in ['hi', 'hello', 'hey', 'thanks', 'ok', 'yes', 'no']:
                continue
                
            return {
                "is_command_request": True,
                "command": "BROWSER_AUTOMATION",
                "action": "web_search",
                "params": {"query": search_query, "engine": "google"},
                "explanation": f"Searching Google for '{search_query}'",
                "confidence": "high"
            }
    
    # Web URL patterns
    if re.search(r'open\s+(?:https?://)?([a-z0-9\.-]+\.[a-z]{2,})', text_lower):
        match = re.search(r'open\s+(https?://[^\s]+|[a-z0-9\.-]+\.[a-z]{2,})', text_lower)
        if match:
            url = match.group(1)
            if not url.startswith('http'):
                url = f"https://{url}"
            return {
                "is_command_request": True,
                "command": f"{url_open_cmd} '{url}'",
                "explanation": f"Open {url}",
                "confidence": "high"
            }

    # Skip AI interpretation for very short messages or obvious conversation
    # This saves time and prevents false positives
    word_count = len(text_lower.split())
    if word_count <= 2:
        # Short messages are usually greetings/responses, not commands
        return {"is_command_request": False}
    
    # Check if text contains any command-like keywords
    # If not, skip AI interpretation (it's likely just conversation)
    command_keywords = [
        'run', 'execute', 'show', 'list', 'display', 'check', 'get', 'find',
        'search', 'open', 'start', 'stop', 'kill', 'install', 'delete', 'remove',
        'create', 'make', 'copy', 'move', 'download', 'upload', 'disk', 'space',
        'process', 'file', 'directory', 'folder', 'system', 'status', 'info'
    ]
    
    has_command_keyword = any(keyword in text_lower for keyword in command_keywords)
    if not has_command_keyword:
        # No command keywords found, this is likely just conversation
        return {"is_command_request": False}

    try:
        ai_response = get_ai_response(prompt)
        
        # Find JSON in response
        json_match = re.search(r'\{.*\}', ai_response, re.DOTALL)
        if json_match:
            parsed = json.loads(json_match.group())
            return parsed
        return {"is_command_request": False}
    except Exception as e:
        logger.error(f"Error interpreting command request: {e}")
        return {"is_command_request": False}

def process_identity_update(user_request, user_id=None):
    """Use AI to update the bot's identity based on natural language request"""
    return call_service(
        'identity',
        'process_identity_update',
        user_request,
        user_id,
        read_identity,
        ask_ollama,
        default="❌ Identity service is not available right now.",
    )

def detect_tracking_request(text, user_id):
    """Detect and handle generic tracking requests using AI"""
    return call_service('tracking', 'detect_tracking_request', text, user_id, get_ai_response, default=None)

def interpret_tracking_request(text, user_id):
    """Use AI to interpret what the user wants to track"""
    return call_service('tracking', 'interpret_tracking_request', text, user_id, get_ai_response, default=None)

def interpret_report_request(text, user_id):
    """Use AI to understand what report the user wants"""
    return call_service('tracking', 'interpret_report_request', text, user_id, get_ai_response, default=None)

def generate_tracking_report(user_id, category, days=7):
    """Generate a comprehensive report for any tracking category"""
    return call_service(
        'tracking',
        'generate_tracking_report',
        user_id,
        category,
        days,
        default="❌ Tracking service is not available right now.",
    )

def detect_sleep_tracking(text, user_id):
    """Detect and handle sleep tracking requests"""
    return call_service('tracking', 'detect_sleep_tracking', text, user_id, default=None)

def generate_sleep_report(user_id, days=7):
    """Generate a comprehensive sleep report"""
    return call_service('tracking', 'generate_sleep_report', user_id, days, default="❌ Tracking service is not available right now.")

def check_capability_question(text, user_id=None):
    """Check if user is asking about bot's capabilities"""
    text_lower = text.lower().strip()
    
    # Time queries - just learn the pattern but DON'T return a response
    # Let the LLM handle the actual response for natural conversation
    time_questions = ["what time is it", "what's the time", "whats the time", "current time", 
                     "tell me the time", "what time", "time now", "what is the time",
                     "show me the time", "give me the time"]
    
    # Check for standalone time queries
    if text_lower in ["time", "time?", "time please", "the time"]:
        # 📚 Learn this pattern
        if user_id:
            learn_from_interaction(user_id, text_lower, 'time', 'time_query')
        # Return None to let LLM handle the response
        return None
    
    # Check for time questions in the text
    if any(q in text_lower for q in time_questions):
        # 📚 Learn this pattern
        if user_id:
            learn_from_interaction(user_id, text_lower, 'time', 'time_query')
        # Return None to let LLM handle the response
        return None
    
    # Catch-all for any question with "time" that we might have missed
    if re.search(r'\btime\b.*\?|what.*\btime\b|\btime\b.*what', text_lower):
        # 📚 Learn this pattern
        if user_id:
            learn_from_interaction(user_id, text_lower, 'time', 'time_query')
        # Return None to let LLM handle the response
        return None
    
    # Name/identity questions - give concise responses
    name_questions = ["what is your name", "what's your name", "whats your name", 
                     "tell me your name", "your name"]
    if any(q in text_lower for q in name_questions):
        bot_name = get_bot_name()
        return f"My name is {bot_name}."
    
    who_questions = ["who are you", "who r u"]
    if any(q in text_lower for q in who_questions):
        bot_name = get_bot_name()
        return f"I'm {bot_name}, your personal AI assistant."
    
    # User ID questions
    id_questions = ["my telegram id", "my user id", "my chat id", "what is my id",
                   "what's my id", "show my id", "my telegram user"]
    if any(q in text_lower for q in id_questions):
        # This will be handled in handle_message with actual user_id
        return "USER_ID_REQUEST"
    
    # Command execution questions
    command_questions = ["can you run command", "can you execute command", "can you run shell",
                        "can you execute shell", "do you run system command"]
    if any(q in text_lower for q in command_questions):
        return """Yes! I can execute shell commands in multiple ways:

🔧 Command Execution:
• /run <command> - Direct execution
• "run command <cmd>" - Via chat
• Just ask naturally: "show me the files here"

I understand natural language and will figure out the right command!"""

    # Cron/scheduling questions
    schedule_questions = ["can you schedule", "can you set reminder", "can you automate",
                         "do you support cron", "can you run tasks automatically"]
    if any(q in text_lower for q in schedule_questions):
        return call_service('cron', 'get_capability_summary', default="""Yes! I have powerful scheduling capabilities:

    ⏰ Cron Job Features:
    • /addjob - Create scheduled tasks
    • /listjobs - View all scheduled jobs
    • /removejob - Delete jobs
    • Natural language: "remind me every day at 9am"

    I can schedule:
    • Skill checks
    • Command execution
    • Custom reminders
    • Cleanup tasks""")

    # General capability questions
    what_can_you_do = ["what can you do", "what are your features", "what can you help",
                       "what are your capabilities", "help me"]
    if any(q in text_lower for q in what_can_you_do):
        return _build_dynamic_capabilities_text()

    return None  # Not a capability question

def interpret_identity_request(text):
    """Detect and interpret requests to update bot identity"""
    return call_service('identity', 'interpret_identity_request', text, default=None)

def schedule_job(job):
    """Schedule a single job"""
    try:
        # Parse schedule (cron format: minute hour day month day_of_week)
        # Or simple format: "every 1 hour", "every 30 minutes", "daily at 09:00"
        # Or time range: "every X hour(s)/minute(s) from HH:MM to HH:MM"
        schedule = job['schedule']
        
        # Check for time range format (e.g., "every hour from 6pm to 5:30 am")
        time_range_match = re.search(r'every\s+(\d+)?\s*(hour|minute)s?\s+from\s+(.+?)\s+to\s+(.+)', schedule, re.IGNORECASE)
        if time_range_match:
            interval_value = int(time_range_match.group(1)) if time_range_match.group(1) else 1
            interval_unit = time_range_match.group(2).lower()
            start_time_str = time_range_match.group(3).strip()
            end_time_str = time_range_match.group(4).strip()
            
            # Parse time strings (handle formats like "6pm", "18:00", "5:30 am")
            def parse_time(time_str):
                time_str = time_str.lower().strip()
                # Handle am/pm format
                if 'am' in time_str or 'pm' in time_str:
                    is_pm = 'pm' in time_str
                    time_str = time_str.replace('am', '').replace('pm', '').strip()
                    if ':' in time_str:
                        hour, minute = map(int, time_str.split(':'))
                    else:
                        hour = int(time_str)
                        minute = 0
                    if is_pm and hour != 12:
                        hour += 12
                    elif not is_pm and hour == 12:
                        hour = 0
                else:
                    # 24-hour format
                    if ':' in time_str:
                        hour, minute = map(int, time_str.split(':'))
                    else:
                        hour = int(time_str)
                        minute = 0
                return hour, minute
            
            start_hour, start_minute = parse_time(start_time_str)
            end_hour, end_minute = parse_time(end_time_str)
            
            # For time ranges, use cron-style scheduling with hour ranges
            # Since APScheduler doesn't directly support "from-to" for intervals,
            # we'll use cron with hour ranges
            if interval_unit == 'hour':
                # Schedule every N hours within the time range
                # For simplicity, we'll create multiple cron jobs for each hour in range
                if start_hour <= end_hour:
                    # Same day range
                    hour_range = f"{start_hour}-{end_hour}"
                else:
                    # Crosses midnight (e.g., 18:00 to 05:30)
                    hour_range = f"{start_hour}-23,0-{end_hour}"
                
                scheduler.add_job(
                    execute_cron_job,
                    'cron',
                    hour=hour_range,
                    minute=start_minute,
                    args=[job['job_type'], job['params']],
                    id=job['name']
                )
            else:  # minute interval
                # For minute intervals, schedule at that minute every hour within range
                if start_hour <= end_hour:
                    hour_range = f"{start_hour}-{end_hour}"
                else:
                    hour_range = f"{start_hour}-23,0-{end_hour}"
                
                scheduler.add_job(
                    execute_cron_job,
                    'cron',
                    hour=hour_range,
                    minute=f"*/{interval_value}",
                    args=[job['job_type'], job['params']],
                    id=job['name']
                )
        # Simple schedule parsing
        elif schedule.startswith("every"):
            parts = schedule.split()
            if "minute" in schedule:
                minutes = int(parts[1])
                scheduler.add_job(
                    execute_cron_job,
                    'interval',
                    minutes=minutes,
                    args=[job['job_type'], job['params']],
                    id=job['name']
                )
            elif "hour" in schedule:
                hours = int(parts[1])
                scheduler.add_job(
                    execute_cron_job,
                    'interval',
                    hours=hours,
                    args=[job['job_type'], job['params']],
                    id=job['name']
                )
        # One-time schedule: "in X hours/minutes"
        elif schedule.startswith("in "):
            from datetime import datetime, timedelta
            parts = schedule.split()
            value = int(parts[1])
            unit = parts[2].lower()
            
            if 'hour' in unit:
                run_date = datetime.now() + timedelta(hours=value)
            elif 'minute' in unit:
                run_date = datetime.now() + timedelta(minutes=value)
            else:
                run_date = datetime.now() + timedelta(hours=value)  # default
            
            scheduler.add_job(
                execute_cron_job,
                'date',
                run_date=run_date,
                args=[job['job_type'], job['params']],
                id=job['name']
            )
        # One-time schedule: "at YYYY-MM-DD HH:MM" or "at HH:MM"
        elif schedule.startswith("at "):
            from datetime import datetime
            datetime_str = schedule[3:].strip()
            
            # Try full datetime format first
            try:
                if len(datetime_str) > 10:  # Likely has date
                    run_date = datetime.strptime(datetime_str, '%Y-%m-%d %H:%M')
                else:  # Just time, assume today
                    time_part = datetime_str
                    today = datetime.now().strftime('%Y-%m-%d')
                    run_date = datetime.strptime(f"{today} {time_part}", '%Y-%m-%d %H:%M')
                    
                    # If time has passed today, schedule for tomorrow
                    if run_date < datetime.now():
                        from datetime import timedelta
                        run_date += timedelta(days=1)
                
                scheduler.add_job(
                    execute_cron_job,
                    'date',
                    run_date=run_date,
                    args=[job['job_type'], job['params']],
                    id=job['name']
                )
            except ValueError as e:
                logger.error(f"Error parsing datetime: {datetime_str} - {e}")
                return False
        elif "daily at" in schedule:
            time_str = schedule.split("at")[1].strip()
            hour, minute = time_str.split(":")
            scheduler.add_job(
                execute_cron_job,
                'cron',
                hour=int(hour),
                minute=int(minute),
                args=[job['job_type'], job['params']],
                id=job['name']
            )
        else:
            # Cron format: minute hour day month day_of_week
            parts = schedule.split()
            if len(parts) == 5:
                scheduler.add_job(
                    execute_cron_job,
                    CronTrigger.from_crontab(schedule),
                    args=[job['job_type'], job['params']],
                    id=job['name']
                )
            else:
                # Unknown format
                logger.error(f"Unknown schedule format: {schedule}")
                return False
        
        logger.info(f"Scheduled job: {job['name']} - {schedule}")
        return True
    except Exception as e:
        logger.error(f"Error scheduling job {job['name']}: {e}", exc_info=True)
        return False

def load_cron_jobs():
    """Load and schedule all cron jobs from database"""
    jobs = database.get_all_cron_jobs()
    for job in jobs:
        if job['enabled']:
            schedule_job(job)
    logger.info(f"Loaded {len(jobs)} cron jobs")

def parse_cron_from_text(text):
    """Parse natural language cron job request using AI"""
    return call_service('cron_nl', 'parse_cron_from_text', text, get_ai_response, default=None)
def create_cron_from_natural_language(text, user_id):
    """Create a cron job from natural language"""
    return call_service('cron_nl', 'create_cron_from_natural_language', text, user_id, get_ai_response, schedule_job, default=None)

def manage_cron_job_nl(text, user_id):
    """Manage cron jobs (edit, enable, disable, delete) from natural language"""
    return call_service('cron_nl', 'manage_cron_job_nl', text, user_id, get_ai_response, schedule_job, scheduler, default=None)

def interpret_cron_management(text, user_id):
    """Use AI to interpret cron job management requests"""
    return call_service('cron_nl', 'interpret_cron_management', text, user_id, get_ai_response, default=None)

# ---------- Access Control ----------
def is_user_allowed(user_id):
    # Get allowed users from database (comma-separated list)
    allowed = database.get_config("allowed_users", "")
    if not allowed:
        return True  # if not set, allow everyone
    allowed_list = [uid.strip() for uid in allowed.split(",")]
    return str(user_id) in allowed_list

# ---------- Telegram Handlers ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
        help_text = _build_dynamic_start_help()
        await safe_reply(update.message, help_text)

async def plugin_command_bridge(update: Update, context: ContextTypes.DEFAULT_TYPE, command_name: str):
    if not is_user_allowed(update.effective_user.id):
        await update.message.reply_text("You are not authorized to use this bot.")
        return

    payload = invoke_first_available_method(
        'build_command_response',
        command_name,
        context.args or [],
        str(update.effective_user.id),
        default={
            'pre_message': None,
            'reply': 'This service is not available right now. Restart the bot so it can initialize.',
            'parse_mode': None,
        },
    )

    pre_message = (payload or {}).get('pre_message')
    reply_text = (payload or {}).get('reply', '')
    parse_mode_key = (payload or {}).get('parse_mode')

    if pre_message:
        await update.message.reply_text(pre_message)

    if parse_mode_key == 'HTML':
        await send_html_in_chunks(update.message, reply_text)
        return

    await update.message.reply_text(reply_text)


async def send_html_in_chunks(message, text, chunk_size=3400):
    content = (text or "").strip()
    if not content:
        await message.reply_text("(empty response)")
        return

    if len(content) <= chunk_size:
        await message.reply_text(content, parse_mode=ParseMode.HTML)
        return

    chunks = []
    remaining = content
    while len(remaining) > chunk_size:
        split_idx = remaining.rfind('\n', 0, chunk_size)
        if split_idx < int(chunk_size * 0.5):
            split_idx = chunk_size
        chunks.append(remaining[:split_idx].strip())
        remaining = remaining[split_idx:].lstrip()
    if remaining:
        chunks.append(remaining)

    total = len(chunks)
    for index, chunk in enumerate(chunks, 1):
        if total > 1:
            prefix = f"<i>(Part {index}/{total})</i>\n"
            await message.reply_text(prefix + chunk, parse_mode=ParseMode.HTML)
        else:
            await message.reply_text(chunk, parse_mode=ParseMode.HTML)


async def addjob_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /addjob command"""
    if not is_user_allowed(update.effective_user.id):
        await safe_reply(update.message, "You are not authorized to use this bot.", preferred_mode=ParseMode.HTML)
        return
    
    help_text = call_service(
        'cron',
        'get_addjob_help_text',
        default="""Add a cron job:

/addjob <name> <type> <schedule> [params]

Types:
• send_message - Send a message
• custom_command - Run a command
• cleanup - Cleanup old data
• check_email - Run scheduled email check

Schedule examples:
• "every 30 minutes"
• "every 1 hour"
• "daily at 09:00"
• "0 9 * * *" (cron: 9 AM daily)

Examples:
/addjob morning_email check_email "daily at 08:00"
/addjob hourly_check check_email "every 1 hour"
/addjob reminder send_message "daily at 12:00" message="Take a break!"
""",
    )
    
    if len(context.args) < 3:
        await safe_reply(update.message, help_text, preferred_mode=ParseMode.HTML)
        return
    
    name = context.args[0]
    job_type = context.args[1]
    
    # Parse schedule (handle quoted strings)
    full_text = " ".join(context.args[2:])
    
    # Extract schedule from quotes if present
    if '"' in full_text:
        schedule_start = full_text.index('"') + 1
        schedule_end = full_text.index('"', schedule_start)
        schedule = full_text[schedule_start:schedule_end]
        params_text = full_text[schedule_end+1:].strip()
    else:
        # Take next 3-5 words as schedule
        schedule = " ".join(context.args[2:5])
        params_text = " ".join(context.args[5:]) if len(context.args) > 5 else ""
    
    # Parse params
    params = {}
    if params_text:
        for param in params_text.split():
            if '=' in param:
                key, value = param.split('=', 1)
                params[key] = value.strip('"')
    
    # Add job to database
    success, message = database.add_cron_job(name, job_type, schedule, params)
    
    if success:
        # Schedule it
        job = {
            'name': name,
            'job_type': job_type,
            'schedule': schedule,
            'params': params,
            'enabled': True
        }
        if schedule_job(job):
            await safe_reply(update.message, f"✅ Cron job <code>{name}</code> added and scheduled!", preferred_mode=ParseMode.HTML)
        else:
            await safe_reply(update.message, "⚠️ Job added to database but failed to schedule. Check logs.", preferred_mode=ParseMode.HTML)
    else:
        await safe_reply(update.message, f"❌ {message}", preferred_mode=ParseMode.HTML)

async def listjobs_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /listjobs command"""
    if not is_user_allowed(update.effective_user.id):
        await safe_reply(update.message, "You are not authorized to use this bot.", preferred_mode=ParseMode.HTML)
        return
    
    jobs = database.get_all_cron_jobs()
    
    if not jobs:
        await safe_reply(update.message, "No cron jobs configured.", preferred_mode=ParseMode.HTML)
        return
    
    jobs = sorted(jobs, key=lambda job: int(job.get('id', 0)))

    result = "⏰ <b>Scheduled Cron Jobs</b>:\n\n"
    for index, job in enumerate(jobs, 1):
        status = "✅" if job['enabled'] else "❌"
        safe_name = html.escape(str(job.get('name', '')))
        safe_type = html.escape(str(job.get('job_type', '')))
        safe_schedule = html.escape(str(job.get('schedule', '')))
        result += f"{status} <b>{index}.</b> <code>{safe_name}</code> (ID: <code>{job['id']}</code>)\n"
        result += f"   Type: {safe_type}\n"
        result += f"   Schedule: {safe_schedule}\n"
        if job['params']:
            safe_params = html.escape(str(job['params']))
            result += f"   Params: {safe_params}\n"
        result += "\n"
    
    result += "\nUse <code>/removejob &lt;id|name&gt;</code> to delete a job"
    await safe_reply(update.message, result, preferred_mode=ParseMode.HTML)

async def removejob_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /removejob command"""
    if not is_user_allowed(update.effective_user.id):
        await safe_reply(update.message, "You are not authorized to use this bot.", preferred_mode=ParseMode.HTML)
        return
    
    if not context.args:
        await safe_reply(update.message, "Usage: <code>/removejob &lt;job_id_or_name&gt;</code>", preferred_mode=ParseMode.HTML)
        return
    
    target = context.args[0].strip()
    name = target
    job_id = None

    if target.isdigit():
        job_id = int(target)
        jobs = database.get_all_cron_jobs()
        matched_job = next((job for job in jobs if int(job.get('id', 0)) == job_id), None)
        if not matched_job:
            await safe_reply(update.message, f"❌ Job ID <code>{job_id}</code> not found.", preferred_mode=ParseMode.HTML)
            return
        name = matched_job['name']
    
    # Remove from scheduler
    try:
        scheduler.remove_job(name)
    except:
        pass  # Job might not be scheduled
    
    # Remove from database
    try:
        if database.remove_cron_job(name):
            if job_id is not None:
                await safe_reply(update.message, f"✅ Cron job removed: ID <code>{job_id}</code> • <code>{name}</code>", preferred_mode=ParseMode.HTML)
            else:
                await safe_reply(update.message, f"✅ Cron job <code>{name}</code> removed!", preferred_mode=ParseMode.HTML)
        else:
            if job_id is not None:
                await safe_reply(update.message, f"❌ Job ID <code>{job_id}</code> not found.", preferred_mode=ParseMode.HTML)
            else:
                await safe_reply(update.message, f"❌ Job <code>{name}</code> not found.", preferred_mode=ParseMode.HTML)
    except Exception as exc:
        logger.error(f"Failed to remove cron job '{name}': {exc}", exc_info=True)
        await safe_reply(update.message, "❌ Failed to remove the job. Please try again.", preferred_mode=ParseMode.HTML)

async def run_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /run command - execute a shell command"""
    if not is_user_allowed(update.effective_user.id):
        await update.message.reply_text("You are not authorized to use this bot.")
        return
    
    if not context.args:
        await update.message.reply_text("""Usage: /run <command>

Examples:
  /run ls -la
  /run pwd
  /run df -h
  /run whoami
  /run uptime

⚠️ Be careful with commands!""")
        return
    
    command = " ".join(context.args)
    await update.message.reply_text(f"⏳ Executing: `{command}`...")
    
    result = run_custom_command(command)
    await update.message.reply_text(result)


async def sendto_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /sendto command - send a Telegram message to another chat/user ID."""
    if not is_user_allowed(update.effective_user.id):
        await update.message.reply_text("You are not authorized to use this bot.")
        return

    if len(context.args) < 2:
        await update.message.reply_text(
            "Usage: /sendto <chat_id> <message>\n"
            "Example: /sendto 123456789 Hello from my bot"
        )
        return

    target_chat_raw = context.args[0].strip()
    message_text = " ".join(context.args[1:]).strip()

    if not message_text:
        await update.message.reply_text("❌ Message text is required.")
        return

    try:
        target_chat_id = int(target_chat_raw)
    except ValueError:
        await update.message.reply_text("❌ chat_id must be numeric (for groups it may be negative).")
        return

    try:
        await context.bot.send_message(chat_id=target_chat_id, text=message_text)
        await update.message.reply_text(f"✅ Message sent to chat_id {target_chat_id}.")
    except Exception as exc:
        logger.error(f"Failed to send /sendto message: {exc}")
        await update.message.reply_text(
            "❌ Could not send message. The target user/group must have started or allowed this bot, and the chat_id must be correct."
        )

async def learned_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /learned command - show what the bot has learned"""
    if not is_user_allowed(update.effective_user.id):
        await update.message.reply_text("You are not authorized to use this bot.")
        return
    
    user_id = str(update.effective_user.id)
    
    try:
        # Run blocking database call in thread executor to avoid event loop blocking
        loop = asyncio.get_event_loop()
        learned_rows = await loop.run_in_executor(None, database.get_learned_patterns, user_id)
        
        entries = build_learned_entries(learned_rows)
        if not entries:
            await update.message.reply_text("🎓 I haven't learned any patterns from you yet!\n\nI'll automatically learn from our successful interactions.")
            return

        ordered_types, grouped, display_entries = build_display_learned_entries(entries)

        result = "🎓 <b>What I've Learned About You:</b>\n\n"
        counter = 0
        for pattern_type in ordered_types:
            result += f"<b>{pattern_type.title()}:</b>\n"
            for entry in grouped[pattern_type][:LEARNED_DISPLAY_LIMIT]:
                counter += 1
                confidence = entry['confidence']
                success_count = entry['success_count']
                is_active = confidence >= 0.6
                status_dot = "🟢" if is_active else "🔴"
                status_text = "active" if is_active else "inactive"
                safe_input = html.escape(entry['user_input'] or '')
                safe_intent = html.escape(entry['detected_intent'] or '')
                result += f"{counter}. {status_dot} [#{entry['id']}] <code>{safe_input}</code> → {safe_intent} ({status_text}, used {success_count}x)\n"
            result += "\n"

        result += "<i>I'm learning your language patterns to serve you better!</i>\n\n"
        result += f"Showing {len(display_entries)} entries (up to {LEARNED_DISPLAY_LIMIT} per category).\n"
        result += "Use /deletelearned &lt;number&gt; to remove a specific pattern from this list."
        
        await update.message.reply_text(result, parse_mode=ParseMode.HTML)
        
    except Exception as e:
        logger.error(f"Error showing learned patterns: {e}", exc_info=True)
        await update.message.reply_text(f"❌ Error displaying learned patterns. Check logs for details.")

async def deletelearned_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /deletelearned command - remove a single learned pattern"""
    if not is_user_allowed(update.effective_user.id):
        await update.message.reply_text("You are not authorized to use this bot.")
        return

    if not context.args:
        await update.message.reply_text("Usage: /deletelearned &lt;number&gt; (See /learned for the numbered list)")
        return

    user_id = str(update.effective_user.id)
    try:
        index = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Please provide a valid entry number from /learned.")
        return

    loop = asyncio.get_event_loop()
    learned_rows = await loop.run_in_executor(None, database.get_learned_patterns, user_id)
    entries = build_learned_entries(learned_rows)
    ordered_types, grouped, display_entries = build_display_learned_entries(entries)

    if not display_entries:
        await update.message.reply_text("🎓 I haven't learned any patterns yet.")
        return

    if index < 1 or index > len(display_entries):
        await update.message.reply_text(f"Invalid entry number. Pick a value between 1 and {len(display_entries)}.")
        return

    entry = display_entries[index - 1]
    deleted = await loop.run_in_executor(None, database.delete_learned_pattern, user_id, entry['id'])

    if deleted:
        safe_input = html.escape(entry['user_input'] or '')
        safe_intent = html.escape(entry['detected_intent'] or '')
        result = (
            f"✅ Removed learned pattern {index} [#{entry['id']}]:\n"
            f"<code>{safe_input}</code> → {safe_intent}"
        )
    else:
        result = "⚠️ Unable to delete that learned pattern. Please try again."

    await update.message.reply_text(result, parse_mode=ParseMode.HTML)

async def clearlearned_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /clearlearned command - clear all learned patterns"""
    if not is_user_allowed(update.effective_user.id):
        await update.message.reply_text("You are not authorized to use this bot.")
        return
    
    user_id = str(update.effective_user.id)
    
    try:
        # Run blocking database call in thread executor
        loop = asyncio.get_event_loop()
        deleted_count = await loop.run_in_executor(None, database.clear_learned_patterns, user_id)
        
        if deleted_count > 0:
            result = f"🗑️ *Cleared {deleted_count} learned pattern(s)*\n\n"
            result += "All incorrect patterns have been removed.\n"
            result += "I'll start learning fresh from our new interactions! 🎓"
        else:
            result = "ℹ️ No learned patterns to clear."
        
        await update.message.reply_text(result, parse_mode=ParseMode.HTML)
        
    except Exception as e:
        logger.error(f"Error clearing learned patterns: {e}")
        await update.message.reply_text(f"❌ Error: {str(e)}")

async def config_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /config command - view current configuration"""
    if not is_user_allowed(update.effective_user.id):
        await update.message.reply_text("You are not authorized to use this bot.")
        return
    
    try:
        runtime_keys = set(get_runtime_allowed_config_keys())
        result = "⚙️ <b>Current Configuration:</b>\n\n"
        
        result += "<b>🤖 AI Backend:</b>\n"
        result += f"  Backend: <code>{config.AI_BACKEND}</code>\n"
        if config.AI_BACKEND == "ollama":
            result += f"  Model: <code>{config.OLLAMA_MODEL}</code>\n"
            result += f"  URL: <code>{config.OLLAMA_URL}</code>\n"
        else:
            result += f"  Model: <code>{config.OPENAI_MODEL}</code>\n"
        result += f"  Chat History: <code>{config.CHAT_HISTORY_LIMIT}</code> messages\n\n"
        
        # if 'OPENWEATHER_API_KEY' in runtime_keys:
        #     result += "<b>🌤️ Weather:</b>\n"
        #     result += f"  Default City: <code>{config.DEFAULT_CITY}</code>\n"
        #     result += f"  Country: <code>{config.DEFAULT_COUNTRY_CODE}</code>\n"
        #     result += f"  API Key: <code>{'✓ Set' if config.OPENWEATHER_API_KEY else '✗ Not set'}</code>\n\n"

        result += "<b>💬 Discord:</b>\n"
        result += f"  Bot Token: <code>{'✓ Set' if config.DISCORD_BOT_TOKEN else '✗ Not set'}</code>\n"
        result += f"  Allowed Channels: <code>{config.DISCORD_ALLOWED_CHANNEL_IDS if config.DISCORD_ALLOWED_CHANNEL_IDS else 'All channels'}</code>\n\n"

        result += "<b>📱 WhatsApp (Twilio):</b>\n"
        result += f"  Account SID: <code>{'✓ Set' if config.WHATSAPP_TWILIO_ACCOUNT_SID else '✗ Not set'}</code>\n"
        result += f"  Auth Token: <code>{'✓ Set' if config.WHATSAPP_TWILIO_AUTH_TOKEN else '✗ Not set'}</code>\n"
        result += f"  Sender Number: <code>{config.WHATSAPP_TWILIO_NUMBER if config.WHATSAPP_TWILIO_NUMBER else '✗ Not set'}</code>\n"
        result += f"  Verify Token: <code>{'✓ Set' if config.WHATSAPP_WEBHOOK_VERIFY_TOKEN else '✗ Not set'}</code>\n\n"

        result += "<b>🧠 RAG:</b>\n"
        result += f"  Enabled: <code>{'Yes' if config.RAG_ENABLED else 'No'}</code>\n"
        result += f"  Knowledge Dir: <code>{config.RAG_KB_DIR}</code>\n"
        result += f"  Chunk Size: <code>{config.RAG_CHUNK_SIZE}</code> chars\n"
        result += f"  Top K: <code>{config.RAG_TOP_K}</code>\n"
        result += f"  Max Context: <code>{config.RAG_MAX_CONTEXT_CHARS}</code> chars\n\n"
        
        result += "<i>Use /setconfig &lt;key&gt; &lt;value&gt; to change settings</i>"
        
        await update.message.reply_text(result, parse_mode=ParseMode.HTML)
        
    except Exception as e:
        logger.error(f"Error showing config: {e}")
        await update.message.reply_text(f"❌ Error: {str(e)}")

async def setconfig_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /setconfig command - update configuration"""
    if not is_user_allowed(update.effective_user.id):
        await update.message.reply_text("You are not authorized to use this bot.")
        return
    
    if len(context.args) < 2:
        available_keys = get_runtime_allowed_config_keys()
        key_lines = "\n".join([f"• <code>{key}</code>" for key in available_keys])
        help_text = """⚙️ <b>Set Configuration</b>

<b>Usage:</b> <code>/setconfig KEY VALUE</code>

<b>Available Keys:</b>
""" + key_lines + """

<b>Examples:</b>
<code>/setconfig OLLAMA_MODEL llama3.2</code>
<code>/setconfig DEFAULT_CITY Tokyo</code>
<code>/setconfig CHAT_HISTORY_LIMIT 10</code>
<code>/setconfig RAG_ENABLED true</code>
<code>/setconfig RAG_KB_DIR knowledge</code>
<code>/setconfig DISCORD_BOT_TOKEN your_token_here</code>
<code>/setconfig WHATSAPP_TWILIO_NUMBER whatsapp:+14155238886</code>"""
        await update.message.reply_text(help_text, parse_mode=ParseMode.HTML)
        return
    
    key = context.args[0].upper()
    value = ' '.join(context.args[1:])
    
    if not is_runtime_allowed_config_key(key):
        await update.message.reply_text(f"❌ Invalid config key: {key}\n\nUse /setconfig without arguments to see available keys.")
        return
    
    try:
        typed_value = apply_config_update(key, value)

        if key in ['DISCORD_BOT_TOKEN', 'DISCORD_ALLOWED_CHANNEL_IDS']:
            ensure_discord_bridge_running()
        
        result = f"✅ <b>Configuration Updated</b>\n\n"
        result += f"<code>{key}</code> = <code>{typed_value}</code>\n\n"
        result += "<i>Changes are active immediately!</i>"
        
        await update.message.reply_text(result, parse_mode=ParseMode.HTML)
        logger.info(f"Config updated: {key} = {typed_value}")
        
    except ValueError:
        await update.message.reply_text("❌ Invalid value type. Numeric keys require a number.")
    except Exception as e:
        logger.error(f"Error setting config: {e}")
        await update.message.reply_text(f"❌ Error: {str(e)}")


async def gateway_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /gateway command."""
    if not is_user_allowed(update.effective_user.id):
        await update.message.reply_text("You are not authorized to use this bot.")
        return

    args = context.args or []
    if not args:
        help_text = (
            "🛡️ <b>Gateway Commands</b>\n\n"
            "<b>Usage:</b>\n"
            "• <code>/gateway list</code>\n"
            "• <code>/gateway get KEY</code>\n"
            "• <code>/gateway set KEY VALUE</code>\n"
            "• <code>/onboard</code> (show onboarding status)\n\n"
            "You can also use <code>/setconfig KEY VALUE</code>."
        )
        await update.message.reply_text(help_text, parse_mode=ParseMode.HTML)
        return

    action = args[0].lower()
    if action == 'list':
        lines = ["🛡️ <b>Gateway Config Keys</b>"]
        for key in get_runtime_allowed_config_keys():
            current = str(getattr(config, key, ''))
            lines.append(f"• <code>{key}</code> = <code>{html.escape(_mask_value(key, current))}</code>")
        await send_html_in_chunks(update.message, "\n".join(lines), chunk_size=3200)
        return

    if action == 'get':
        if len(args) < 2:
            await update.message.reply_text("Usage: /gateway get KEY")
            return
        key = args[1].upper()
        if not is_runtime_allowed_config_key(key):
            await update.message.reply_text(f"❌ Invalid config key: {key}")
            return
        value = str(getattr(config, key, ''))
        await update.message.reply_text(
            f"<b>{key}</b> = <code>{html.escape(_mask_value(key, value))}</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    if action == 'set':
        if len(args) < 3:
            await update.message.reply_text("Usage: /gateway set KEY VALUE")
            return
        key = args[1].upper()
        value = ' '.join(args[2:])
        try:
            typed_value = apply_config_update(key, value)
            if key in ['DISCORD_BOT_TOKEN', 'DISCORD_ALLOWED_CHANNEL_IDS']:
                ensure_discord_bridge_running()
            await update.message.reply_text(
                f"✅ <b>Gateway Updated</b>\n\n<code>{key}</code> = <code>{html.escape(_mask_value(key, str(typed_value)))}</code>",
                parse_mode=ParseMode.HTML,
            )
            return
        except KeyError:
            await update.message.reply_text(f"❌ Invalid config key: {key}")
            return
        except Exception as exc:
            await update.message.reply_text(f"❌ Failed to update config: {exc}")
            return

    await update.message.reply_text("Unknown gateway action. Use /gateway for help.")


async def onboard_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /onboard command - show onboarding readiness and missing keys."""
    if not is_user_allowed(update.effective_user.id):
        await update.message.reply_text("You are not authorized to use this bot.")
        return

    missing = get_missing_onboarding_keys()
    if not missing:
        await update.message.reply_text(
            "✅ Onboarding looks complete.\nUse /gateway list or /setconfig to edit settings.",
            parse_mode=ParseMode.HTML,
        )
        return

    missing_items = "\n".join([f"• <code>{key}</code>" for key in missing])
    message = (
        "⚠️ <b>Onboarding Incomplete</b>\n\n"
        "Missing required configuration:\n"
        f"{missing_items}\n\n"
        "Update from chat with <code>/gateway set KEY VALUE</code> or <code>/setconfig KEY VALUE</code>.\n"
        "From CLI/binary: <code>./pybot onboard</code>"
    )
    await update.message.reply_text(message, parse_mode=ParseMode.HTML)

async def tools_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show Ai Assistant-like power features available in chat"""
    if not is_user_allowed(update.effective_user.id):
        await update.message.reply_text("You are not authorized to use this bot.")
        return

    help_text = """🛠️ <b>Advanced Tools (Ai Assistant-style)</b>

<b>File Operations</b>
• <code>/listfiles [path]</code>
• <code>/readfile &lt;path&gt;</code>
• <code>/writefile &lt;path&gt; &lt;content&gt;</code>
• <code>/searchcode &lt;text&gt;</code>

<b>Git Operations</b>
• <code>/git status</code>, <code>/git log</code>, <code>/git diff</code>
• <code>/git add &lt;file&gt;</code>, <code>/git commit &lt;msg&gt;</code>
• <code>/git push</code>, <code>/git pull</code>, <code>/git branch</code>

<b>Runtime & Config</b>
• <code>/exec &lt;python_code&gt;</code>
• <code>/config</code>
• <code>/setconfig &lt;key&gt; &lt;value&gt;</code>
• <code>/plan &lt;task&gt;</code>
• <code>/nextstep</code>
• <code>/planreset</code>

<b>Natural language examples</b>
• "list files"
• "read file bot.py"
• "git status"
• "show config"
• "set config CHAT_HISTORY_LIMIT 10"
"""
    await update.message.reply_text(help_text, parse_mode=ParseMode.HTML)

def parse_plan_steps(ai_text):
    """Parse plan steps from AI output."""
    return advanced_features.parse_plan_steps(ai_text)

async def plan_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Create an execution plan from a natural language task."""
    if not is_user_allowed(update.effective_user.id):
        await update.message.reply_text("You are not authorized to use this bot.")
        return

    user_id = str(update.effective_user.id)

    if len(context.args) < 1:
        # Show existing plan if available
        saved_steps = await asyncio.to_thread(database.get_user_context, user_id, 'active_plan_steps')
        saved_index = await asyncio.to_thread(database.get_user_context, user_id, 'active_plan_index')
        saved_task = await asyncio.to_thread(database.get_user_context, user_id, 'active_plan_task')
        if saved_steps and saved_task:
            try:
                steps = json.loads(saved_steps)
                index = int(saved_index or 0)
                result = f"🗂️ <b>Current Plan</b>\n\n<b>Task:</b> {saved_task}\n\n"
                for i, step in enumerate(steps, 1):
                    marker = "➡️" if i - 1 == index else "✅" if i - 1 < index else "▫️"
                    result += f"{marker} {i}. {step}\n"
                result += "\nUse <code>/nextstep</code> to execute the next step."
                await update.message.reply_text(result, parse_mode=ParseMode.HTML)
                return
            except Exception:
                pass

        await update.message.reply_text("🧭 Usage: <code>/plan &lt;what you want to do&gt;</code>", parse_mode=ParseMode.HTML)
        return

    task = ' '.join(context.args).strip()
    await update.message.reply_text("🧠 Building step-by-step plan...")

    prompt = (
        "Create a short actionable execution plan for this software task. "
        "Return ONLY numbered steps, one per line, max 6 steps. "
        "Each step should be concrete and executable.\n\n"
        f"Task: {task}"
    )

    ai_plan = get_ai_response(prompt, user_id)
    steps = parse_plan_steps(ai_plan)
    if not steps:
        steps = [
            "Understand the requirement and inspect relevant files.",
            "Implement focused code changes.",
            "Run checks/tests and verify behavior.",
            "Summarize results and next actions."
        ]

    await asyncio.to_thread(database.save_user_context, user_id, 'active_plan_task', task)
    await asyncio.to_thread(database.save_user_context, user_id, 'active_plan_steps', json.dumps(steps))
    await asyncio.to_thread(database.save_user_context, user_id, 'active_plan_index', '0')

    result = f"🗂️ <b>Plan Created</b>\n\n<b>Task:</b> {task}\n\n"
    for i, step in enumerate(steps, 1):
        result += f"{i}. {step}\n"
    result += "\nUse <code>/nextstep</code> to run step 1."

    await update.message.reply_text(result, parse_mode=ParseMode.HTML)

async def nextstep_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Execute the next step from the active plan when possible."""
    if not is_user_allowed(update.effective_user.id):
        await update.message.reply_text("You are not authorized to use this bot.")
        return

    user_id = str(update.effective_user.id)

    saved_steps = await asyncio.to_thread(database.get_user_context, user_id, 'active_plan_steps')
    saved_index = await asyncio.to_thread(database.get_user_context, user_id, 'active_plan_index')
    saved_task = await asyncio.to_thread(database.get_user_context, user_id, 'active_plan_task')

    if not saved_steps:
        await update.message.reply_text("❌ No active plan. Create one using <code>/plan &lt;task&gt;</code>.", parse_mode=ParseMode.HTML)
        return

    try:
        steps = json.loads(saved_steps)
        index = int(saved_index or 0)
    except Exception:
        await update.message.reply_text("❌ Plan data is corrupted. Create a new one with /plan.")
        return

    if index >= len(steps):
        await update.message.reply_text("✅ Plan already completed.")
        return

    step = steps[index]
    await update.message.reply_text(f"▶️ <b>Executing Step {index + 1}:</b> {step}", parse_mode=ParseMode.HTML)

    interpreted = interpret_advanced_nl_request(step)
    if interpreted:
        action = interpreted.get("action")
        if action == "listfiles":
            path = interpreted.get("path", ".")
            context.args = [path] if path else []
            await listfiles_command(update, context)
        elif action == "readfile":
            path = interpreted.get("path", "")
            context.args = [path] if path else []
            await readfile_command(update, context)
        elif action == "searchcode":
            query = interpreted.get("query", "")
            context.args = query.split() if query else []
            await search_code_command(update, context)
        elif action == "git":
            context.args = interpreted.get("args", [])
            await git_command(update, context)
        elif action == "config":
            await config_command(update, context)
        elif action == "setconfig":
            key = interpreted.get("key", "")
            value = interpreted.get("value", "")
            context.args = [key, value]
            await setconfig_command(update, context)
        else:
            await update.message.reply_text(f"ℹ️ Step parsed but not executable automatically: {step}")
    else:
        await update.message.reply_text(
            "ℹ️ This step needs manual work:\n"
            f"{step}\n\n"
            "You can ask me to run a specific command after this.")

    new_index = index + 1
    await asyncio.to_thread(database.save_user_context, user_id, 'active_plan_index', str(new_index))

    if new_index < len(steps):
        await update.message.reply_text(f"⏭️ Next: Step {new_index + 1}. Run <code>/nextstep</code> again.", parse_mode=ParseMode.HTML)
    else:
        await update.message.reply_text(f"✅ Plan complete for task: {saved_task}")

async def planreset_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Clear active plan data for the current user."""
    if not is_user_allowed(update.effective_user.id):
        await update.message.reply_text("You are not authorized to use this bot.")
        return

    user_id = str(update.effective_user.id)
    await asyncio.to_thread(database.save_user_context, user_id, 'active_plan_task', '')
    await asyncio.to_thread(database.save_user_context, user_id, 'active_plan_steps', '')
    await asyncio.to_thread(database.save_user_context, user_id, 'active_plan_index', '0')

    await update.message.reply_text("🧹 Active plan cleared. Use <code>/plan &lt;task&gt;</code> to start a new one.", parse_mode=ParseMode.HTML)

def interpret_advanced_nl_request(text):
    """Interpret Assistant-like natural language tool requests."""
    return advanced_features.interpret_advanced_nl_request(text)

def update_env_file(key, value, env_path='.env'):
    """Update or add a key-value pair in .env file."""
    advanced_features.update_env_file(key, value, env_path=env_path)

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /status command - show comprehensive bot status"""
    if not is_user_allowed(update.effective_user.id):
        await update.message.reply_text("You are not authorized to use this bot.")
        return
    
    # Get user ID for learning stats
    user_id = update.effective_user.id
    
    try:
        PSUTIL_AVAILABLE = True
    except ImportError:
        PSUTIL_AVAILABLE = False
    
    # Get bot start time (approximate)
    if PSUTIL_AVAILABLE:
        try:
            process = psutil.Process(os.getpid())
            uptime_seconds = time.time() - process.create_time()
            uptime = str(timedelta(seconds=int(uptime_seconds)))
        except:
            uptime = "unknown"
    else:
        uptime = "unknown"
    
    # Database stats
    try:
        db_size = os.path.getsize('MyPyBot.db')
        db_size_mb = db_size / (1024 * 1024)
        
        # Count records in key tables
        messages_count = database.get_message_count()
        jobs = database.get_all_cron_jobs()
        jobs_count = len(jobs)
        active_jobs = len([j for j in jobs if j['enabled']])
    except:
        db_size_mb = 0
        messages_count = 0
        jobs_count = 0
        active_jobs = 0
    
    # AI Backend info
    ai_backend = config.AI_BACKEND
    model = config.OLLAMA_MODEL if ai_backend == "ollama" else "OpenAI GPT"
    
    # API Keys status (discovered from plugin metadata)
    api_status = get_plugin_api_status(config)
    
    # System info
    if PSUTIL_AVAILABLE:
        try:
            cpu_percent = psutil.cpu_percent(interval=0.5)
            memory = psutil.virtual_memory()
            memory_percent = memory.percent
            disk = psutil.disk_usage('/')
            disk_percent = disk.percent
            system_stats = f"""  • CPU: {cpu_percent:.1f}%
  • Memory: {memory_percent:.1f}%
  • Disk: {disk_percent:.1f}%"""
        except:
            system_stats = "  • System stats unavailable"
    else:
        system_stats = "  • Install psutil for system stats"
    
    # Scheduler info
    scheduler_running = scheduler.running
    scheduler_jobs = len(scheduler.get_jobs())
    
    # Learning stats
    try:
        learned = database.get_learned_patterns(user_id)
        learned_count = len(learned)
        user_ctx = database.get_user_context(user_id)
        preferences_count = len(user_ctx) if user_ctx else 0
    except:
        learned_count = 0
        preferences_count = 0

    bot_name = get_bot_name()
    scheduler_status = "Running ✅" if scheduler_running else "Stopped ❌"
    enabled_skills_count = len([skill for skill in get_skill_definitions().values() if skill.enabled])
    api_status_text = "\n".join([f"• {item}" for item in api_status])
    system_stats_text = system_stats

    status = (
        f"🤖 <b>{bot_name} Status</b>\n\n"
        f"<b>🧠 AI</b>\n"
        f"• Backend: <code>{ai_backend}</code>\n"
        f"• Model: <code>{model}</code>\n\n"
        f"<b>💾 Database</b>\n"
        f"• Size: <code>{db_size_mb:.2f} MB</code>\n"
        f"• Messages: <code>{messages_count:,}</code>\n"
        f"• Scheduled Jobs: <code>{active_jobs}/{jobs_count}</code> active\n\n"
        f"<b>🎓 Learning</b>\n"
        f"• Learned Patterns: <code>{learned_count}</code>\n"
        f"• User Preferences: <code>{preferences_count}</code>\n\n"
        f"<b>⏰ Scheduler</b>\n"
        f"• Status: {scheduler_status}\n"
        f"• Active Jobs In Memory: <code>{scheduler_jobs}</code>\n\n"
        f"<b>🔑 API Keys</b>\n"
        f"{api_status_text}\n\n"
        f"<b>⚙️ System</b>\n"
        f"• Python: <code>{sys.version.split()[0]}</code>\n"
        f"• Uptime: <code>{uptime}</code>\n"
        f"{system_stats_text}\n\n"
        f"<b>📊 Summary</b>\n"
        f"• Enabled Skills: <code>{enabled_skills_count}</code>\n"
        f"• Status: <b>Operational ⚡</b>"
    )

    await safe_reply(update.message, status, preferred_mode=ParseMode.HTML)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    """Log unhandled errors and notify user when possible."""
    logger.error("Unhandled exception in update handler", exc_info=context.error)
    try:
        if update and hasattr(update, "effective_message") and update.effective_message:
            await safe_reply(update.effective_message, "❌ Something went wrong while processing your request. Please try again.")
    except Exception:
        pass


async def safe_reply(message, text, preferred_mode=None):
    """Send Telegram message with graceful parse-mode fallback."""
    if preferred_mode is None:
        return await message.reply_text(text)

    try:
        return await message.reply_text(text, parse_mode=preferred_mode)
    except Exception as first_error:
        logger.debug(f"safe_reply preferred mode failed: {first_error}")

    if preferred_mode == ParseMode.HTML:
        try:
            return await message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
        except Exception as second_error:
            logger.debug(f"safe_reply markdown fallback failed: {second_error}")
    elif preferred_mode == ParseMode.MARKDOWN:
        try:
            return await message.reply_text(text, parse_mode=ParseMode.HTML)
        except Exception as second_error:
            logger.debug(f"safe_reply html fallback failed: {second_error}")

    plain_text = re.sub(r'<[^>]+>', '', text)
    plain_text = plain_text.replace('*', '').replace('_', '').replace('`', '')
    return await message.reply_text(plain_text)


def format_ai_reply_for_telegram(text):
    """Convert common LLM markdown to Telegram-safe HTML."""
    if not text:
        return ""

    placeholders = {}

    def stash(match, tag):
        key = f"__TG_PLACEHOLDER_{len(placeholders)}__"
        content = match.group(1)
        placeholders[key] = f"<{tag}>{html.escape(content)}</{tag}>"
        return key

    # Protect code blocks and inline code first
    text = re.sub(r'```\s*([\s\S]*?)\s*```', lambda m: stash(m, "pre"), text)
    text = re.sub(r'`([^`\n]+)`', lambda m: stash(m, "code"), text)

    # Escape the rest
    text = html.escape(text)

    # Headings (Telegram has no heading support, map to bold)
    text = re.sub(r'(?m)^\s*#{1,6}\s+(.+?)\s*$', r'<b>\1</b>', text)

    # Bold/italic basics
    text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
    text = re.sub(r'__(.+?)__', r'<b>\1</b>', text)
    text = re.sub(r'(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)', r'<i>\1</i>', text)

    # Simple bullet normalization
    text = re.sub(r'(?m)^\s*[-*]\s+', '• ', text)

    # Restore code placeholders
    for key, value in placeholders.items():
        text = text.replace(html.escape(key), value)
        text = text.replace(key, value)

    return text

# ---------- Claude-like Advanced Features ----------

async def readfile_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /readfile command - read any file in the project"""
    if not is_user_allowed(update.effective_user.id):
        await update.message.reply_text("You are not authorized to use this bot.")
        return
    
    if len(context.args) < 1:
        await update.message.reply_text("📄 <b>Read File</b>\n\nUsage: <code>/readfile &lt;filepath&gt;</code>\n\nExample: <code>/readfile bot.py</code>", parse_mode=ParseMode.HTML)
        return
    
    filepath = ' '.join(context.args)
    
    try:
        project_dir = os.path.abspath('.')
        ok, message, preview, truncated = advanced_features.read_file_preview(filepath, project_dir, preview_chars=3500)
        if not ok:
            await update.message.reply_text(message)
            return
        
        # Check file size
        file_size = os.path.getsize(filepath)
        if file_size > 1024 * 1024:  # 1MB limit
            await update.message.reply_text(f"❌ File too large: {file_size/1024/1024:.2f}MB (max 1MB)")
            return
        
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        
        # Split into chunks if too long for Telegram (4096 char limit)
        max_length = 3800
        if len(content) <= max_length:
            result = f"📄 <b>{filepath}</b>\n\n<pre>{content}</pre>"
            await update.message.reply_text(result, parse_mode=ParseMode.HTML)
        else:
            lines = content.split('\n')
            chunks = []
            current_chunk = []
            current_length = 0
            
            for line in lines:
                if current_length + len(line) + 1 > max_length:
                    chunks.append('\n'.join(current_chunk))
                    current_chunk = [line]
                    current_length = len(line)
                else:
                    current_chunk.append(line)
                    current_length += len(line) + 1
            
            if current_chunk:
                chunks.append('\n'.join(current_chunk))
            
            for i, chunk in enumerate(chunks):
                result = f"📄 <b>{filepath}</b> (Part {i+1}/{len(chunks)})\n\n<pre>{chunk}</pre>"
                await update.message.reply_text(result, parse_mode=ParseMode.HTML)
                await asyncio.sleep(0.5)  # Avoid rate limiting
        
    except Exception as e:
        logger.error(f"Error reading file: {e}")
        await update.message.reply_text(f"❌ Error: {str(e)}")

async def writefile_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /writefile command - write content to a file"""
    if not is_user_allowed(update.effective_user.id):
        await update.message.reply_text("You are not authorized to use this bot.")
        return
    
    if len(context.args) < 2:
        help_text = """📝 <b>Write File</b>

<b>Usage:</b> <code>/writefile &lt;filepath&gt; &lt;content&gt;</code>

<b>Example:</b>
<code>/writefile test.txt Hello World!</code>

<i>⚠️ This will overwrite the file if it exists!</i>"""
        await update.message.reply_text(help_text, parse_mode=ParseMode.HTML)
        return
    
    filepath = context.args[0]
    content = ' '.join(context.args[1:])
    
    try:
        # Security check
        abs_path = os.path.abspath(filepath)
        project_dir = os.path.abspath('.')
        
        if not abs_path.startswith(project_dir):
            await update.message.reply_text("❌ Access denied: Can only write files within project directory.")
            return
        
        # Create directory if it doesn't exist
        dir_path = os.path.dirname(filepath)
        if dir_path and not os.path.exists(dir_path):
            os.makedirs(dir_path)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        
        file_size = os.path.getsize(filepath)
        result = f"✅ <b>File Written</b>\n\n"
        result += f"📄 Path: <code>{filepath}</code>\n"
        result += f"📊 Size: {file_size} bytes\n"
        result += f"✏️ Content length: {len(content)} characters"
        
        await update.message.reply_text(result, parse_mode=ParseMode.HTML)
        logger.info(f"File written: {filepath}")
        
    except Exception as e:
        logger.error(f"Error writing file: {e}")
        await update.message.reply_text(f"❌ Error: {str(e)}")

async def listfiles_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /listfiles command - list files in directory"""
    if not is_user_allowed(update.effective_user.id):
        await update.message.reply_text("You are not authorized to use this bot.")
        return
    
    path = context.args[0] if context.args else '.'
    
    try:
        project_dir = os.path.abspath('.')
        ok, message, dirs, files = advanced_features.list_directory_summary(path, project_dir, max_items=50)
        if not ok:
            await update.message.reply_text(message)
            return
        
        result = f"📁 <b>{path or 'Current Directory'}</b>\n\n"
        
        if dirs:
            result += "<b>📁 Directories:</b>\n"
            for d in dirs[:50]:  # Limit to 50
                result += f"  📁 {d}/\n"
            if len(dirs) > 50:
                result += f"  <i>... and {len(dirs)-50} more</i>\n"
            result += "\n"
        
        if files:
            result += "<b>📄 Files:</b>\n"
            for f in files[:50]:  # Limit to 50
                size = os.path.getsize(os.path.join(path, f))
                if size < 1024:
                    size_str = f"{size}B"
                elif size < 1024*1024:
                    size_str = f"{size/1024:.1f}KB"
                else:
                    size_str = f"{size/1024/1024:.1f}MB"
                result += f"  📄 {f} <i>({size_str})</i>\n"
            if len(files) > 50:
                result += f"  <i>... and {len(files)-50} more</i>\n"
        
        if not dirs and not files:
            result += "<i>Empty directory</i>"
        
        result += f"\n<b>Total:</b> {len(dirs)} dirs, {len(files)} files"
        
        await update.message.reply_text(result, parse_mode=ParseMode.HTML)
        
    except Exception as e:
        logger.error(f"Error listing files: {e}")
        await update.message.reply_text(f"❌ Error: {str(e)}")

async def git_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /git command - git operations"""
    if not is_user_allowed(update.effective_user.id):
        await update.message.reply_text("You are not authorized to use this bot.")
        return
    
    if len(context.args) < 1:
        help_text = """🔀 <b>Git Operations</b>

<b>Available commands:</b>
• <code>/git status</code> - Show git status
• <code>/git log</code> - Show recent commits
• <code>/git diff</code> - Show changes
• <code>/git add &lt;file&gt;</code> - Stage file
• <code>/git commit &lt;message&gt;</code> - Commit changes
• <code>/git push</code> - Push to remote
• <code>/git pull</code> - Pull from remote
• <code>/git branch</code> - List branches

<i>⚠️ Use with caution!</i>"""
        await update.message.reply_text(help_text, parse_mode=ParseMode.HTML)
        return
    
    git_cmd = context.args[0].lower()
    git_args = context.args[1:] if len(context.args) > 1 else []
    
    try:
        if git_cmd == 'status':
            result = subprocess.run(['git', 'status', '--short'], capture_output=True, text=True, timeout=10)
            output = result.stdout.strip() if result.stdout else "✅ Working tree clean"
            response = f"🔀 <b>Git Status</b>\n\n<pre>{output}</pre>"
            
        elif git_cmd == 'log':
            result = subprocess.run(['git', 'log', '--oneline', '-10'], capture_output=True, text=True, timeout=10)
            output = result.stdout.strip() if result.stdout else "No commits"
            response = f"📜 <b>Recent Commits</b>\n\n<pre>{output}</pre>"
            
        elif git_cmd == 'diff':
            result = subprocess.run(['git', 'diff', '--stat'], capture_output=True, text=True, timeout=10)
            output = result.stdout.strip() if result.stdout else "No changes"
            response = f"📊 <b>Git Diff</b>\n\n<pre>{output}</pre>"
            
        elif git_cmd == 'add':
            if not git_args:
                response = "❌ Please specify file(s) to add"
            else:
                result = subprocess.run(['git', 'add'] + git_args, capture_output=True, text=True, timeout=10)
                if result.returncode == 0:
                    response = f"✅ <b>Files staged:</b> {' '.join(git_args)}"
                else:
                    response = f"❌ Error:\n<pre>{result.stderr}</pre>"
                    
        elif git_cmd == 'commit':
            if not git_args:
                response = "❌ Please provide commit message"
            else:
                commit_msg = ' '.join(git_args)
                result = subprocess.run(['git', 'commit', '-m', commit_msg], capture_output=True, text=True, timeout=10)
                if result.returncode == 0:
                    response = f"✅ <b>Committed:</b>\n<pre>{result.stdout}</pre>"
                else:
                    response = f"❌ Error:\n<pre>{result.stderr}</pre>"
                    
        elif git_cmd == 'push':
            result = subprocess.run(['git', 'push'], capture_output=True, text=True, timeout=30)
            if result.returncode == 0:
                response = f"✅ <b>Pushed to remote</b>\n<pre>{result.stdout or 'Success'}</pre>"
            else:
                response = f"❌ Error:\n<pre>{result.stderr}</pre>"
                
        elif git_cmd == 'pull':
            result = subprocess.run(['git', 'pull'], capture_output=True, text=True, timeout=30)
            if result.returncode == 0:
                response = f"✅ <b>Pulled from remote</b>\n<pre>{result.stdout}</pre>"
            else:
                response = f"❌ Error:\n<pre>{result.stderr}</pre>"
                
        elif git_cmd == 'branch':
            result = subprocess.run(['git', 'branch'], capture_output=True, text=True, timeout=10)
            output = result.stdout.strip() if result.stdout else "No branches"
            response = f"🌿 <b>Branches</b>\n\n<pre>{output}</pre>"
            
        else:
            response = f"❌ Unknown git command: {git_cmd}\n\nUse /git without arguments to see available commands."
        
        await update.message.reply_text(response, parse_mode=ParseMode.HTML)
        
    except subprocess.TimeoutExpired:
        await update.message.reply_text("❌ Command timed out")
    except FileNotFoundError:
        await update.message.reply_text("❌ Git not found on system")
    except Exception as e:
        logger.error(f"Git command error: {e}")
        await update.message.reply_text(f"❌ Error: {str(e)}")

async def execcode_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /exec command - execute Python code"""
    if not is_user_allowed(update.effective_user.id):
        await update.message.reply_text("You are not authorized to use this bot.")
        return
    
    if len(context.args) < 1:
        help_text = """💻 <b>Execute Python Code</b>

<b>Usage:</b> <code>/exec &lt;python_code&gt;</code>

<b>Examples:</b>
<code>/exec print(2 + 2)</code>
<code>/exec import sys; print(sys.version)</code>

<i>⚠️ Code runs in isolated environment with timeout</i>"""
        await update.message.reply_text(help_text, parse_mode=ParseMode.HTML)
        return
    
    code = ' '.join(context.args)
    
    try:
        # Create isolated environment with restricted builtins
        restricted_globals = {
            '__builtins__': {
                'print': print,
                'len': len,
                'range': range,
                'str': str,
                'int': int,
                'float': float,
                'list': list,
                'dict': dict,
                'tuple': tuple,
                'set': set,
                'bool': bool,
                'sum': sum,
                'min': min,
                'max': max,
                'abs': abs,
                'round': round,
                'sorted': sorted,
                'enumerate': enumerate,
                'zip': zip,
                'map': map,
                'filter': filter,
            }
        }
        
        # Capture output
        import io
        from contextlib import redirect_stdout
        
        output_buffer = io.StringIO()
        
        # Run code with timeout
        with redirect_stdout(output_buffer):
            exec(code, restricted_globals)
        
        output = output_buffer.getvalue()
        
        if output:
            result = f"✅ <b>Code Executed</b>\n\n<b>Output:</b>\n<pre>{output}</pre>"
        else:
            result = "✅ <b>Code executed successfully</b> (no output)"
        
        await update.message.reply_text(result, parse_mode=ParseMode.HTML)
        
    except SyntaxError as e:
        await update.message.reply_text(f"❌ <b>Syntax Error:</b>\n<pre>{str(e)}</pre>", parse_mode=ParseMode.HTML)
    except Exception as e:
        await update.message.reply_text(f"❌ <b>Error:</b>\n<pre>{str(e)}</pre>", parse_mode=ParseMode.HTML)

async def search_code_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /searchcode command - search for text in project files"""
    if not is_user_allowed(update.effective_user.id):
        await update.message.reply_text("You are not authorized to use this bot.")
        return
    
    if len(context.args) < 1:
        await update.message.reply_text("🔍 <b>Search Code</b>\n\nUsage: <code>/searchcode &lt;search_term&gt;</code>", parse_mode=ParseMode.HTML)
        return
    
    search_term = ' '.join(context.args)
    
    try:
        matches = advanced_features.search_codebase(search_term)
        
        if matches:
            result_text = f"🔍 <b>Found {len(matches)} matches for '{search_term}':</b>\n\n"
            
            # Limit to first 20 matches
            for match in matches[:20]:
                result_text += f"<code>{match}</code>\n"
            
            if len(matches) > 20:
                result_text += f"\n<i>... and {len(matches) - 20} more matches</i>"
        else:
            result_text = f"❌ No matches found for '{search_term}'"
        
        await update.message.reply_text(result_text, parse_mode=ParseMode.HTML)
        
    except Exception as e:
        logger.error(f"Code search error: {e}")
        await update.message.reply_text(f"❌ Error: {str(e)}")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = str(user.id)
    user_name = user.full_name or user.username or "Unknown"
    user_message = update.message.text

    # Access control
    if not is_user_allowed(user_id):
        await update.message.reply_text("You are not authorized to use this bot.")
        return

    logger.info(f"Message from {user_name} ({user_id}): {user_message}")

    nlu_hint = nlu_service.detect_intent(user_message) if nlu_service else None
    nlu_intent = (nlu_hint or {}).get('intent')
    nlu_confidence = (nlu_hint or {}).get('confidence')
    if nlu_intent:
        logger.info(f"NLU intent hint: {nlu_intent} (confidence: {nlu_confidence:.3f})")

    # Show typing (best effort only; should never abort handling)
    try:
        await update.message.chat.send_action(action="typing")
    except Exception as exc:
        logger.warning(f"Typing indicator failed, continuing: {exc}")

    # Ai Assistant-like planning workflow via natural language
    msg_lower = user_message.lower().strip()
    if msg_lower.startswith("plan:") or msg_lower.startswith("make a plan for ") or msg_lower.startswith("create a plan for "):
        task = user_message.split(':', 1)[1].strip() if ':' in user_message else re.sub(r'^(make|create) a plan for\s+', '', user_message, flags=re.IGNORECASE).strip()
        context.args = task.split() if task else []
        await plan_command(update, context)
        return
    if msg_lower in ["next step", "run next step", "execute next step"]:
        await nextstep_command(update, context)
        return
    if msg_lower in ["reset plan", "clear plan", "cancel plan", "plan reset"]:
        await planreset_command(update, context)
        return

    # Ai Assistant-like natural language tool routing
    advanced_request = interpret_advanced_nl_request(user_message)
    if advanced_request:
        action = advanced_request.get("action")

        try:
            if action == "listfiles":
                path = advanced_request.get("path", ".")
                project_dir = os.path.abspath('.')
                ok, message, dirs, files = advanced_features.list_directory_summary(path, project_dir, max_items=40)
                if not ok:
                    result = message
                else:
                    result = f"📁 <b>{path}</b>\n\n"
                    if dirs:
                        result += "<b>Directories:</b>\n" + "\n".join([f"📁 {d}/" for d in dirs[:40]]) + "\n\n"
                    if files:
                        result += "<b>Files:</b>\n" + "\n".join([f"📄 {f}" for f in files[:40]])
                    if not dirs and not files:
                        result += "<i>Empty directory</i>"
                await update.message.reply_text(result, parse_mode=ParseMode.HTML)
                learn_command_like_success(user_id, user_message, "advanced:listfiles", result)
                database.save_message("telegram", user_id, user_name, user_message, result)
                return

            if action == "readfile":
                path = advanced_request.get("path")
                project_dir = os.path.abspath('.')
                ok, message, preview, truncated = advanced_features.read_file_preview(path, project_dir, preview_chars=3500)
                if not ok:
                    result = message
                else:
                    safe_preview = preview.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
                    result = f"📄 <b>{path}</b>\n\n<pre>{safe_preview}</pre>"
                    if truncated:
                        result += "\n<i>Output truncated. Use /readfile for full chunked output.</i>"
                await update.message.reply_text(result, parse_mode=ParseMode.HTML)
                learn_command_like_success(user_id, user_message, "advanced:readfile", result)
                database.save_message("telegram", user_id, user_name, user_message, result)
                return

            if action == "searchcode":
                query = advanced_request.get("query", "")
                matches = advanced_features.search_codebase(query)
                if matches:
                    safe_matches = "\n".join(matches[:20]).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
                    result = f"🔍 <b>Found {len(matches)} matches:</b>\n\n<pre>{safe_matches}</pre>"
                else:
                    result = f"❌ No matches found for: <code>{query}</code>"
                await update.message.reply_text(result, parse_mode=ParseMode.HTML)
                learn_command_like_success(user_id, user_message, "advanced:searchcode", result)
                database.save_message("telegram", user_id, user_name, user_message, result)
                return

            if action == "git":
                args = advanced_request.get("args", [])
                result_run = subprocess.run(['git'] + args, capture_output=True, text=True, timeout=20)
                output = (result_run.stdout or result_run.stderr or "No output").strip()
                safe_output = output.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
                result = f"🔀 <b>Git {' '.join(args)}</b>\n\n<pre>{safe_output[:3500]}</pre>"
                await update.message.reply_text(result, parse_mode=ParseMode.HTML)
                learn_command_like_success(user_id, user_message, f"command_exec:git {' '.join(args)}", output)
                database.save_message("telegram", user_id, user_name, user_message, result)
                return

            if action == "config":
                await config_command(update, context)
                return

            if action == "setconfig":
                key = advanced_request.get("key", "")
                value = advanced_request.get("value", "")
                if not is_runtime_allowed_config_key(key):
                    await update.message.reply_text(f"❌ Invalid config key: {key}")
                    return
                try:
                    typed_value = apply_config_update(key, value)

                    if key in ['DISCORD_BOT_TOKEN', 'DISCORD_ALLOWED_CHANNEL_IDS']:
                        ensure_discord_bridge_running()

                    result = f"✅ <b>Configuration Updated</b>\n\n<code>{key}</code> = <code>{typed_value}</code>"
                    await update.message.reply_text(result, parse_mode=ParseMode.HTML)
                    learn_command_like_success(user_id, user_message, f"advanced:setconfig:{key}", result)
                    database.save_message("telegram", user_id, user_name, user_message, result)
                except ValueError:
                    await update.message.reply_text("❌ Invalid value type for CHAT_HISTORY_LIMIT.")
                return

        except Exception as e:
            logger.error(f"Advanced NL request error: {e}")
            await update.message.reply_text(f"❌ Tool execution error: {str(e)}")
            return

    # Check if this is an explicit command execution request with keywords
    command_keywords = ["run command", "execute command", "run the command", "execute this"]
    msg_lower = user_message.lower()

    trello_request = call_service('trello', 'detect_request', user_message, default=None)
    if trello_request:
        trello_result = call_service(
            'trello',
            'handle_request',
            trello_request,
            user_id,
            get_user_context=lambda uid, key: database.get_user_context(uid, key),
            save_user_context=lambda uid, key, value: database.save_user_context(uid, key, value),
            default="❌ Trello service is not available right now.",
        )
        await update.message.reply_text(trello_result)
        database.save_message("telegram", user_id, user_name, user_message, trello_result)
        return
    
    if any(keyword in msg_lower for keyword in command_keywords):
        # Extract the command
        for keyword in command_keywords:
            if keyword in msg_lower:
                # Get everything after the keyword
                command = user_message[msg_lower.index(keyword) + len(keyword):].strip()
                # Remove common punctuation
                command = command.strip(':').strip()
                
                if command:
                    result = run_custom_command(command)
                    await update.message.reply_text(result)
                    learn_command_like_success(user_id, user_message, f"command_exec:{command}", result)
                    database.save_message("telegram", user_id, user_name, user_message, result)
                    return
                else:
                    await update.message.reply_text("Please specify a command to run.\nExample: run command ls -la")
                    return

    # Use AI to interpret if this is a command request (smart detection)
    interpretation = interpret_command_request(user_message, user_id)
    
    if interpretation.get("is_command_request") and interpretation.get("confidence") in ["high", "medium"]:
        command = interpretation.get("command", "")
        
        if command:
            # Check if it's browser automation
            if command == "BROWSER_AUTOMATION":
                action = interpretation.get("action", "")
                params = interpretation.get("params", {})
                explanation = interpretation.get("explanation", "Automating browser")
                
                await update.message.reply_text(f"🤖 {explanation}...")
                learn_command_like_success(user_id, user_message, f"browser_auto:{action}", explanation)
                
                # Run browser automation in background thread to avoid blocking

                def run_automation():
                    result = automate_browser(action, **params)
                    # Send result back to user
                    asyncio.run(update.message.reply_text(result))
                
                thread = threading.Thread(target=run_automation)
                thread.start()
                database.save_message("telegram", user_id, user_name, user_message, explanation)
                return
            else:
                # Regular command execution
                result = run_custom_command(command)
                await update.message.reply_text(result)
                learn_command_like_success(user_id, user_message, f"command_exec:{command}", result)
                database.save_message("telegram", user_id, user_name, user_message, result)
                return

    # Check if this is a cron job management request (edit, delete, enable, disable, list)
    if call_service('cron_nl', 'looks_like_management_request', user_message, default=False):
        mgmt_result = manage_cron_job_nl(user_message, user_id)
        
        if mgmt_result:
            await update.message.reply_text(mgmt_result)
            database.save_message("telegram", user_id, user_name, user_message, mgmt_result)
            return

    # Check if this is a cron job creation request
    if call_service('cron_nl', 'looks_like_cron_request', user_message, default=False):
        # Try to parse as cron job
        cron_result = create_cron_from_natural_language(user_message, user_id)
        
        if cron_result:
            # It was a cron job request
            await update.message.reply_text(cron_result, parse_mode=ParseMode.MARKDOWN)
            database.save_message("telegram", user_id, user_name, user_message, cron_result)
            return

    # Check if this is a tracking/reporting request (sleep, exercise, study, etc.)
    tracking_result = detect_tracking_request(user_message, user_id)
    if tracking_result:
        await update.message.reply_text(tracking_result)
        database.save_message("telegram", user_id, user_name, user_message, tracking_result)
        return

    plugin_outcome = invoke_first_available_method(
        'handle_interaction',
        user_message,
        user_id,
        nlu_intent=nlu_intent,
        get_user_context=lambda uid, key: database.get_user_context(uid, key),
        save_user_context=lambda uid, key, value: database.save_user_context(uid, key, value),
        check_learned_patterns=check_learned_patterns,
        learn_from_interaction=learn_from_interaction,
        ask_ollama=ask_ollama,
        default=None,
    )
    if plugin_outcome and plugin_outcome.get('handled'):
        plugin_reply = plugin_outcome.get('reply', '')
        parse_mode_key = plugin_outcome.get('parse_mode', 'MARKDOWN')
        parse_mode = getattr(ParseMode, parse_mode_key, ParseMode.MARKDOWN)
        await update.message.reply_text(plugin_reply, parse_mode=parse_mode)
        database.save_message("telegram", user_id, user_name, user_message, plugin_reply)
        return

    # NOTE: Reminders are now handled as one-time cron jobs
    # Check if this is a shopping list request
    shopping_detection = detect_shopping_request(user_message, user_id)
    if shopping_detection:
        action = shopping_detection.get('action')
        if action == 'add':
            items_text = shopping_detection.get('items')
            result = handle_shopping_add(items_text, user_id)
        elif action == 'list':
            result = handle_shopping_list(user_id)
        elif action == 'clear':
            result = handle_shopping_clear(user_id)
        else:
            result = "❌ Unknown shopping list action"
        
        await update.message.reply_text(result, parse_mode=ParseMode.HTML)
        database.save_message("telegram", user_id, user_name, user_message, result)
        return

    # Check if this is a timer request
    timer_detection = detect_timer_request(user_message, user_id)
    if timer_detection:
        action = timer_detection.get('action')
        if action == 'create':
            duration = timer_detection.get('duration')
            result = handle_timer_create(duration, user_id)
        elif action == 'list':
            result = handle_timer_list(user_id)
        else:
            result = "❌ Unknown timer action"
        
        await update.message.reply_text(result, parse_mode=ParseMode.HTML)
        database.save_message("telegram", user_id, user_name, user_message, result)
        return

    # Check if asking about bot capabilities or identity (BEFORE calculations)
    capability_response = check_capability_question(user_message, user_id)
    if capability_response:
        if capability_response == "USER_ID_REQUEST":
            # Special case: user asking for their Telegram ID
            result = f"👤 Your Telegram User ID: `{user_id}`\n\nYou can use this ID to configure bot access."
            await update.message.reply_text(result, parse_mode=ParseMode.MARKDOWN)
            database.save_message("telegram", user_id, user_name, user_message, result)
            return
        else:
            await update.message.reply_text(capability_response, parse_mode=ParseMode.MARKDOWN)
            database.save_message("telegram", user_id, user_name, user_message, capability_response)
            return

    # Check if this is a calculation or unit conversion request
    calc_detection = detect_calculation_request(user_message)
    if calc_detection:
        await update.message.reply_text("🔢 Calculating...")
        result = handle_calculation(user_message)
        await update.message.reply_text(result)
        database.save_message("telegram", user_id, user_name, user_message, result)
        return

    # Check if this is a Wikipedia request
    wiki_detection = None
    if nlu_intent == 'wikipedia':
        wiki_detection = {'action': 'wiki', 'query': user_message}
    if not wiki_detection:
        wiki_detection = detect_wikipedia_request(user_message, user_id)
    if wiki_detection and nlu_intent != 'search' and not detect_search_request(user_message, user_id):
        query = wiki_detection.get('query')
        await update.message.reply_text(f"📚 Searching Wikipedia for '{query}'...")
        result = search_wikipedia(query)
        await update.message.reply_text(result, parse_mode=ParseMode.MARKDOWN)
        database.save_message("telegram", user_id, user_name, user_message, result)
        return

    # Check if this is a web search request
    search_detection = None
    if nlu_intent == 'search':
        search_detection = {'action': 'search', 'query': user_message}
    if not search_detection:
        search_detection = detect_search_request(user_message, user_id)
    if search_detection:
        query = search_detection.get('query')
        await update.message.reply_text(f"🔍 Searching for '{query}'...")
        result = search_web(query)
        await update.message.reply_text(result, parse_mode=ParseMode.MARKDOWN)
        database.save_message("telegram", user_id, user_name, user_message, result)
        return

    # Check if this is a news request
    news_detection = None
    if nlu_intent == 'news':
        news_detection = {'action': 'news', 'topic': None}
    if not news_detection:
        news_detection = detect_news_request(user_message, user_id)
    if news_detection:
        topic = news_detection.get('topic')
        msg = f"📰 Fetching news{' about ' + topic if topic else ''}..."
        await update.message.reply_text(msg)
        result = get_news(topic)
        await update.message.reply_text(result, parse_mode=ParseMode.MARKDOWN)
        database.save_message("telegram", user_id, user_name, user_message, result)
        return

    # Check if this is a status request
    status_detection = None
    if nlu_intent == 'status':
        status_detection = {'action': 'status'}
    if not status_detection:
        status_detection = detect_status_request(user_message, user_id)
    if status_detection:
        await status_command(update, context)
        return

    # Check if this is a daily briefing request
    briefing_detection = None
    if nlu_intent == 'briefing':
        briefing_detection = {'action': 'briefing'}
    if not briefing_detection:
        briefing_detection = detect_briefing_request(user_message, user_id)
    if briefing_detection:
        await update.message.reply_text("📋 Preparing your daily briefing...")
        result = generate_daily_briefing(user_id)
        await update.message.reply_text(result, parse_mode=ParseMode.MARKDOWN)
        database.save_message("telegram", user_id, user_name, user_message, result)
        return

    # Check if this is an identity-related request
    identity_request = interpret_identity_request(user_message)
    if identity_request:
        action = identity_request.get("action")
        
        if action == "show_identity":
            current_identity = read_identity()
            await update.message.reply_text(f"🤖 Current Bot Identity:\n\n{current_identity}", parse_mode=ParseMode.MARKDOWN)
            database.save_message("telegram", user_id, user_name, user_message, current_identity)
            return
        
        elif action == "update_identity":
            await update.message.reply_text("🔄 Updating my identity based on your request...")
            
            # Use AI to process the identity update with conversation context
            new_identity = process_identity_update(user_message, user_id)
            
            if new_identity and update_identity(new_identity):
                response = f"✅ Identity updated successfully!\n\n{new_identity}"
                await update.message.reply_text(response, parse_mode=ParseMode.MARKDOWN)
                database.save_message("telegram", user_id, user_name, user_message, response)
            else:
                error_msg = "❌ Failed to update identity. Please try again."
                await update.message.reply_text(error_msg)
                database.save_message("telegram", user_id, user_name, user_message, error_msg)
            return

    # Regular AI response with chat history context
    ai_reply = get_ai_response(user_message, user_id, use_rag=True)
    formatted_ai_reply = format_ai_reply_for_telegram(ai_reply)

    # Send plain text first, then try to apply Telegram-safe HTML formatting
    sent_message = await safe_reply(update.message, ai_reply)
    
    # Try to edit with HTML formatting
    try:
        await sent_message.edit_text(formatted_ai_reply, parse_mode=ParseMode.HTML)
    except Exception as e:
        # If formatting fails, message stays as plain text (already sent)
        logger.debug(f"HTML formatting skipped: {e}")

    # Save to database
    database.save_message("telegram", user_id, user_name, user_message, ai_reply)


def _chunk_text(text, max_length=1900):
    content = (text or "").strip()
    if not content:
        return [""]
    return [content[index:index + max_length] for index in range(0, len(content), max_length)]


def _parse_allowed_channel_ids(raw_value):
    if not raw_value:
        return set()
    values = set()
    for piece in raw_value.split(','):
        cleaned = piece.strip()
        if not cleaned:
            continue
        try:
            values.add(int(cleaned))
        except ValueError:
            logger.warning(f"Invalid DISCORD_ALLOWED_CHANNEL_IDS entry ignored: {cleaned}")
    return values


def process_external_message(platform_name, user_id, user_name, user_message):
    """Process WhatsApp/Discord text using shared AI context flow."""
    if not is_user_allowed(user_id):
        return "You are not authorized to use this bot."

    logger.info(f"[{platform_name}] Message from {user_name} ({user_id}): {user_message}")

    identity_request = interpret_identity_request(user_message)
    if identity_request:
        action = identity_request.get("action")
        if action == "show_identity":
            response = read_identity()
            database.save_message(platform_name, user_id, user_name, user_message, response)
            return response
        if action == "update_identity":
            new_identity = process_identity_update(user_message, user_id)
            if new_identity and update_identity(new_identity):
                response = f"Identity updated successfully.\n\n{new_identity}"
            else:
                response = "Failed to update identity. Please try again."
            database.save_message(platform_name, user_id, user_name, user_message, response)
            return response

    tracking_response = detect_tracking_request(user_message, user_id)
    if tracking_response:
        database.save_message(platform_name, user_id, user_name, user_message, tracking_response)
        return tracking_response

    ai_reply = get_ai_response(user_message, user_id, use_rag=True)
    database.save_message(platform_name, user_id, user_name, user_message, ai_reply)
    return ai_reply


def start_discord_bot():
    """Start Discord listener if DISCORD_BOT_TOKEN is configured."""
    if not config.DISCORD_BOT_TOKEN:
        logger.info("DISCORD_BOT_TOKEN not set. Discord bridge disabled.")
        return

    try:
        import discord
    except ImportError:
        logger.warning("discord.py is not installed. Install requirements to enable Discord bridge.")
        return

    allowed_channel_ids = _parse_allowed_channel_ids(config.DISCORD_ALLOWED_CHANNEL_IDS)
    intents = discord.Intents.default()
    intents.message_content = True
    client = discord.Client(intents=intents)

    @client.event
    async def on_ready():
        logger.info(f"Discord bot connected as {client.user}")

    @client.event
    async def on_message(message):
        if message.author.bot:
            return

        if allowed_channel_ids and message.channel.id not in allowed_channel_ids:
            return

        incoming_text = (message.content or "").strip()
        if not incoming_text:
            return

        discord_user_id = str(message.author.id)
        discord_user_name = message.author.display_name or message.author.name or "Unknown"

        response_text = process_external_message("discord", discord_user_id, discord_user_name, incoming_text)
        for chunk in _chunk_text(response_text, max_length=1900):
            await message.channel.send(chunk)

    try:
        asyncio.run(client.start(config.DISCORD_BOT_TOKEN))
    except Exception as error:
        logger.error(f"Discord bridge stopped due to error: {error}", exc_info=True)


def ensure_discord_bridge_running():
    """Start Discord bridge thread if token exists and thread is not running."""
    global discord_thread

    if not config.DISCORD_BOT_TOKEN:
        return False

    if discord_thread and discord_thread.is_alive():
        return True

    discord_thread = threading.Thread(target=start_discord_bot, daemon=True)
    discord_thread.start()
    logger.info("Discord bridge thread started from dynamic config update")
    return True

# ---------- Flask Web UI ----------
from flask import Flask, Response, render_template_string, request, redirect, url_for, jsonify

app = Flask(__name__)

_jwt_module = None


def get_jwt_module():
    """Lazy-load PyJWT to keep app booting even if dependency is missing."""
    global _jwt_module
    if _jwt_module is not None:
        return _jwt_module
    try:
        _jwt_module = importlib.import_module("jwt")
        return _jwt_module
    except ImportError:
        return None


def generate_dashboard_token(subject="dashboard"):
    jwt_module = get_jwt_module()
    if not config.DASHBOARD_JWT_SECRET or jwt_module is None:
        return None

    payload = {
        "sub": subject,
        "iat": datetime.utcnow(),
        "exp": datetime.utcnow() + timedelta(hours=config.DASHBOARD_JWT_EXPIRE_HOURS),
    }
    return jwt_module.encode(payload, config.DASHBOARD_JWT_SECRET, algorithm=config.DASHBOARD_JWT_ALGORITHM)


def verify_dashboard_token(token):
    jwt_module = get_jwt_module()
    if not config.DASHBOARD_JWT_SECRET:
        return True

    if jwt_module is None:
        logger.warning("DASHBOARD_JWT_SECRET is set but PyJWT is not installed. Dashboard auth cannot be enforced.")
        return True

    if not token:
        return False

    try:
        jwt_module.decode(token, config.DASHBOARD_JWT_SECRET, algorithms=[config.DASHBOARD_JWT_ALGORITHM])
        return True
    except Exception:
        return False


def get_dashboard_token_from_request():
    bearer = request.headers.get("Authorization", "")
    if bearer.startswith("Bearer "):
        return bearer.split(" ", 1)[1].strip()
    return request.args.get("token")


def dashboard_auth_failed():
    return (
        "Unauthorized dashboard access. Provide a valid JWT token as ?token=... or Authorization: Bearer <token>",
        401,
    )

@app.route('/')
def dashboard():
    token = get_dashboard_token_from_request()
    if not verify_dashboard_token(token):
        return dashboard_auth_failed()

    messages = database.get_recent_messages(20)
    # Simple HTML template (inline for simplicity)
    html = '''
    <!doctype html>
    <title>MyPyBot Dashboard</title>
    <h1>🤖 MyPyBot Gateway</h1>
    <h2>Recent Messages</h2>
    <table border="1" cellpadding="5">
        <tr>
            <th>Platform</th>
            <th>User</th>
            <th>Message</th>
            <th>Reply</th>
            <th>Time</th>
        </tr>
        {% for msg in messages %}
        <tr>
            <td>{{ msg[0] }}</td>
            <td>{{ msg[1] }}</td>
            <td>{{ msg[2] }}</td>
            <td>{{ msg[3][:50] }}{% if msg[3]|length > 50 %}...{% endif %}</td>
            <td>{{ msg[4] }}</td>
        </tr>
        {% endfor %}
    </table>
    <p><a href="/config{% if token %}?token={{ token }}{% endif %}">Configuration</a></p>
        <script>
            const token = "{{ token }}";
            const refreshMs = {{ refresh_ms }};

            async function refreshMessages() {
                try {
                    const response = await fetch(`/api/messages?token=${encodeURIComponent(token)}`);
                    if (!response.ok) return;
                    const data = await response.json();
                    const rows = data.messages.map(msg => {
                        const reply = msg.reply && msg.reply.length > 50 ? msg.reply.slice(0, 50) + "..." : (msg.reply || "");
                        return `<tr>
                            <td>${msg.platform || ""}</td>
                            <td>${msg.user || ""}</td>
                            <td>${msg.message || ""}</td>
                            <td>${reply}</td>
                            <td>${msg.timestamp || ""}</td>
                        </tr>`;
                    }).join('');
                    const table = document.querySelector('table');
                    const header = table.querySelector('tr');
                    table.innerHTML = '';
                    table.appendChild(header);
                    table.insertAdjacentHTML('beforeend', rows);
                } catch (e) {
                    console.error('Dashboard refresh failed', e);
                }
            }

            setInterval(refreshMessages, refreshMs);
        </script>
    '''
    return render_template_string(
        html,
        messages=messages,
        token=token or "",
        refresh_ms=max(1000, config.DASHBOARD_AUTO_REFRESH_SECONDS * 1000),
    )


@app.route('/api/messages')
def api_messages():
    token = get_dashboard_token_from_request()
    if not verify_dashboard_token(token):
        return jsonify({"error": "unauthorized"}), 401

    messages = database.get_recent_messages(20)
    data = []
    for msg in messages:
        data.append({
            "platform": msg[0],
            "user": msg[1],
            "message": msg[2],
            "reply": msg[3],
            "timestamp": msg[4],
        })
    return jsonify({"messages": data})


@app.route('/webhook/whatsapp', methods=['POST'])
def whatsapp_webhook():
    """Twilio WhatsApp webhook endpoint."""
    verify_token = request.args.get('token', '')
    if config.WHATSAPP_WEBHOOK_VERIFY_TOKEN and verify_token != config.WHATSAPP_WEBHOOK_VERIFY_TOKEN:
        return ("Unauthorized", 401)

    user_message = (request.form.get('Body') or '').strip()
    user_id = (request.form.get('From') or '').strip() or 'unknown_whatsapp_user'
    user_name = (request.form.get('ProfileName') or '').strip() or 'WhatsApp User'

    if not user_message:
        twiml = "<?xml version=\"1.0\" encoding=\"UTF-8\"?><Response></Response>"
        return Response(twiml, mimetype='application/xml')

    response_text = process_external_message("whatsapp", user_id, user_name, user_message)
    safe_text = html.escape(response_text, quote=False)
    twiml = (
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?>"
        f"<Response><Message>{safe_text}</Message></Response>"
    )
    return Response(twiml, mimetype='application/xml')

@app.route('/config', methods=['GET', 'POST'])
def config_page():
    token = get_dashboard_token_from_request()
    if not verify_dashboard_token(token):
        return dashboard_auth_failed()

    if request.method == 'POST':
        # Update config
        allowed_users = request.form.get('allowed_users', '')
        ai_backend = request.form.get('ai_backend', 'ollama')
        ollama_model = request.form.get('ollama_model', 'llama3.2')
        database.set_config('allowed_users', allowed_users)
        database.set_config('ai_backend', ai_backend)
        database.set_config('ollama_model', ollama_model)
        if token:
            return redirect(url_for('config_page', token=token))
        return redirect(url_for('config_page'))

    # Load current config
    allowed_users = database.get_config('allowed_users', '')
    ai_backend = database.get_config('ai_backend', config.AI_BACKEND)
    ollama_model = database.get_config('ollama_model', config.OLLAMA_MODEL)

    html = '''
    <!doctype html>
    <title>Configuration</title>
    <h1>⚙️ Configuration</h1>
    <form method="post" action="/config{% if token %}?token={{ token }}{% endif %}">
        <label>Allowed User IDs (comma-separated):</label><br>
        <input type="text" name="allowed_users" value="{{ allowed_users }}" size="50"><br><br>
        <label>AI Backend:</label><br>
        <select name="ai_backend">
            <option value="ollama" {% if ai_backend == 'ollama' %}selected{% endif %}>Ollama</option>
            <option value="openai" {% if ai_backend == 'openai' %}selected{% endif %}>OpenAI</option>
        </select><br><br>
        <label>Ollama Model:</label><br>
        <input type="text" name="ollama_model" value="{{ ollama_model }}"><br><br>
        <input type="submit" value="Save">
    </form>
    <p><a href="/{% if token %}?token={{ token }}{% endif %}">Back to Dashboard</a></p>
    '''
    return render_template_string(
        html,
        allowed_users=allowed_users,
        ai_backend=ai_backend,
        ollama_model=ollama_model,
        token=token or "",
    )

def run_flask():
    if config.DASHBOARD_JWT_SECRET:
        token = generate_dashboard_token(subject="web-ui")
        if token:
            logger.info(f"Dashboard JWT enabled. Open: http://127.0.0.1:3000/?token={token}")
        else:
            logger.warning("Dashboard JWT secret is set but token generation failed. Install PyJWT to enable verification.")
    else:
        logger.warning("Dashboard JWT secret not set. Dashboard is open without token.")
    app.run(host='0.0.0.0', port=3000, debug=False, use_reloader=False)


def maybe_sync_skill_metadata_on_startup():
    if not getattr(config, 'AUTO_SYNC_SKILL_METADATA', True):
        logger.info("Skill metadata auto-sync disabled (AUTO_SYNC_SKILL_METADATA=false)")
        return

    only_missing = bool(getattr(config, 'SKILL_METADATA_SYNC_ONLY_MISSING', False))
    try:
        summary = sync_skill_metadata_commands(only_missing=only_missing)
        logger.info(
            "Skill metadata sync complete: updated=%d skipped=%d failed=%d",
            len(summary.get('updated', [])),
            len(summary.get('skipped', [])),
            len(summary.get('failed', [])),
        )
        if summary.get('updated'):
            logger.info("Updated skill metadata: %s", ", ".join(summary['updated']))
        if summary.get('failed'):
            logger.warning("Failed skill metadata sync for: %s", ", ".join(summary['failed']))
    except Exception as exc:
        logger.warning(f"Skill metadata auto-sync failed: {exc}")

async def setup_bot_commands(application):
    """Set up the bot command menu in Telegram"""
    commands = [
        BotCommand("start", "Start the bot and see welcome message"),
        BotCommand("tools", "Show advanced Ai Assistant-like capabilities"),
        BotCommand("plan", "Create a step-by-step execution plan"),
        BotCommand("nextstep", "Execute next step from active plan"),
        BotCommand("planreset", "Clear the current active plan"),
        BotCommand("status", "Show comprehensive bot status and statistics"),
        BotCommand("learned", "Show what the bot has learned about you"),
        BotCommand("clearlearned", "Clear all learned patterns (reset learning)"),
        BotCommand("deletelearned", "Delete a single learned pattern by number"),
        BotCommand("config", "View current configuration settings"),
        BotCommand("setconfig", "Change configuration (key value)"),
        BotCommand("gateway", "config gateway commands"),
        BotCommand("onboard", "Show onboarding status and required setup"),
        BotCommand("readfile", "Read a file from project"),
        BotCommand("writefile", "Write content to a file"),
        BotCommand("listfiles", "List files in directory"),
        BotCommand("searchcode", "Search for text in project files"),
        BotCommand("git", "Git operations (status, commit, push, etc.)"),
        BotCommand("exec", "Execute Python code snippet"),
        # BotCommand("unread", "Check unread emails"),
        # BotCommand("recent", "View recent emails"),
        # BotCommand("search", "Search emails (use: /search <query>)"),
        # BotCommand("email", "Email helper (/email <recent|unread|search|read>)"),
        BotCommand("addjob", "Add a scheduled task manually"),
        BotCommand("listjobs", "List all scheduled tasks and reminders"),
        BotCommand("removejob", "Remove a scheduled task (use: /removejob <name>)"),
        BotCommand("run", "Execute a system command (use: /run <command>)"),
        BotCommand("sendto", "Send Telegram message to chat_id"),
    ]
    await application.bot.set_my_commands(commands)
    logger.info("Bot commands menu registered with Telegram")

# ---------- Main ----------
def main():
    global bot_instance, discord_thread

    if not ensure_runtime_onboarding():
        logger.error("Onboarding/config validation failed. Exiting.")
        return

    maybe_sync_skill_metadata_on_startup()
    
    # Start Flask in a background thread
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    logger.info("Web UI started at http://127.0.0.1:3000")

    if config.DISCORD_BOT_TOKEN:
        discord_thread = threading.Thread(target=start_discord_bot, daemon=True)
        discord_thread.start()
        logger.info("Discord bridge thread started")
    else:
        logger.info("Discord bridge not started (DISCORD_BOT_TOKEN missing)")

    # Start Telegram bot
    app = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()
    bot_instance = app  # Store global reference for cron jobs
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("tools", tools_command))
    app.add_handler(CommandHandler("plan", plan_command))
    app.add_handler(CommandHandler("nextstep", nextstep_command))
    app.add_handler(CommandHandler("planreset", planreset_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("learned", learned_command))
    app.add_handler(CommandHandler("deletelearned", deletelearned_command))
    app.add_handler(CommandHandler("clearlearned", clearlearned_command))
    app.add_handler(CommandHandler("config", config_command))
    app.add_handler(CommandHandler("setconfig", setconfig_command))
    app.add_handler(CommandHandler("gateway", gateway_command))
    app.add_handler(CommandHandler("onboard", onboard_command))
    # File operations
    app.add_handler(CommandHandler("readfile", readfile_command))
    app.add_handler(CommandHandler("writefile", writefile_command))
    app.add_handler(CommandHandler("listfiles", listfiles_command))
    app.add_handler(CommandHandler("searchcode", search_code_command))
    # Git operations
    app.add_handler(CommandHandler("git", git_command))
    # Code execution
    app.add_handler(CommandHandler("exec", execcode_command))
    # Email and tasks
    app.add_handler(CommandHandler("unread", lambda update, context: plugin_command_bridge(update, context, 'unread')))
    app.add_handler(CommandHandler("recent", lambda update, context: plugin_command_bridge(update, context, 'recent')))
    app.add_handler(CommandHandler("search", lambda update, context: plugin_command_bridge(update, context, 'search')))
    app.add_handler(CommandHandler("email", lambda update, context: plugin_command_bridge(update, context, 'email')))
    app.add_handler(CommandHandler("addjob", addjob_command))
    app.add_handler(CommandHandler("listjobs", listjobs_command))
    app.add_handler(CommandHandler("removejob", removejob_command))
    app.add_handler(CommandHandler("run", run_command))
    app.add_handler(CommandHandler("sendto", sendto_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_error_handler(error_handler)

    # Start scheduler and load cron jobs
    scheduler.start()
    load_cron_jobs()
    logger.info("Scheduler started and cron jobs loaded")

    logger.info("Bot started. Polling for messages...")
    
    # Initialize and set up commands before polling
    async def post_init(application):
        await setup_bot_commands(application)
    
    app.post_init = post_init
    app.run_polling()

if __name__ == "__main__":
    cli_exit_code = handle_cli_entrypoint()
    if cli_exit_code is None:
        main()
    else:
        sys.exit(cli_exit_code)