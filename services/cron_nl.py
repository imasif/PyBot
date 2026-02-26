import json
import logging
import re
import time
from datetime import datetime

import database


logger = logging.getLogger(__name__)


class CronNLService:
    def looks_like_management_request(self, text):
        text_lower = (text or '').lower().strip()
        if not text_lower:
            return False

        management_keywords = [
            "delete job", "remove job", "disable job", "enable job", "pause job",
            "edit job", "change job", "update job", "modify job", "list jobs",
            "show jobs", "my jobs", "stop job", "start job", "resume job",
        ]
        return any(keyword in text_lower for keyword in management_keywords)

    def looks_like_cron_request(self, text):
        text_lower = (text or '').lower().strip()
        if not text_lower:
            return False

        cron_keywords = [
            "remind me", "schedule", "every hour", "every day", "every morning",
            "daily at", "everyday", "send me a message", "notify me", "alert me",
        ]
        return any(keyword in text_lower for keyword in cron_keywords)

    def _extract_daily_time(self, text):
        match = re.search(r'\bat\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b', text, re.IGNORECASE)
        if not match:
            return None

        hour = int(match.group(1))
        minute = int(match.group(2) or 0)
        meridiem = (match.group(3) or '').lower()

        if meridiem == 'pm' and hour != 12:
            hour += 12
        elif meridiem == 'am' and hour == 12:
            hour = 0

        if hour < 0 or hour > 23 or minute < 0 or minute > 59:
            return None

        return f"{hour:02d}:{minute:02d}"

    def _parse_rule_based_request(self, text):
        text_lower = (text or '').lower().strip()
        if not text_lower:
            return None

        is_daily = any(token in text_lower for token in ['everyday', 'every day', 'daily'])
        mentions_email = any(token in text_lower for token in ['email', 'emails', 'gmail', 'inbox'])

        if not (is_daily and mentions_email):
            return None

        hhmm = self._extract_daily_time(text_lower) or '09:00'
        return {
            "is_cron_request": True,
            "name": f"daily_email_reminder_{hhmm.replace(':', '')}",
            "type": "check_email",
            "schedule": f"daily at {hhmm}",
            "params": {},
        }

    def _is_email_fetch_intent(self, text, job_type, params):
        normalized_text = (text or '').lower()
        normalized_type = (job_type or '').strip().lower()
        if normalized_type == 'check_email':
            return True

        if normalized_type != 'send_message':
            return False

        message = str((params or {}).get('message', '')).lower()
        mentions_email = any(token in normalized_text for token in ['email', 'emails', 'gmail', 'inbox'])
        asks_check = any(token in normalized_text for token in ['check', 'show', 'get', 'fetch', 'read', 'recent', 'unread'])
        message_email_only = message and any(token in message for token in ['email', 'emails', 'gmail', 'inbox'])
        return (mentions_email and asks_check) or message_email_only

    def parse_cron_from_text(self, text, get_ai_response):
        rule_based = self._parse_rule_based_request(text)
        if rule_based:
            return rule_based

        prompt = f'''Parse this scheduling/reminder request and extract the details in JSON format:
"{text}"

Return ONLY a JSON object with these fields (or null if not a scheduling request):
{{
  "is_cron_request": true/false,
  "name": "job_name",
  "type": "check_email|send_message|custom_command|cleanup",
  "schedule": "schedule format - see examples below",
  "params": {{"key": "value"}}
}}

Schedule formats:
- Recurring: "every X hour(s)", "daily at HH:MM", "every X minute(s)"
- Time range: "every X hour(s) from HH:MM to HH:MM"
- One-time: "at YYYY-MM-DD HH:MM" or "in X hours/minutes"

Examples:
- "remind me to check email every morning at 9am" → {{"is_cron_request": true, "name": "morning_email_check", "type": "check_email", "schedule": "daily at 09:00", "params": {{}}}}
- "send me a message every hour saying check tasks" → {{"is_cron_request": true, "name": "hourly_task_reminder", "type": "send_message", "schedule": "every 1 hour", "params": {{"message": "check tasks"}}}}
- "remind me to call John at 3pm" → {{"is_cron_request": true, "name": "call_john_reminder", "type": "send_message", "schedule": "at {datetime.now().strftime('%Y-%m-%d')} 15:00", "params": {{"message": "call John"}}}}
- "remind me to exercise in 2 hours" → {{"is_cron_request": true, "name": "exercise_reminder", "type": "send_message", "schedule": "in 2 hours", "params": {{"message": "exercise"}}}}
- "what's the weather?" → {{"is_cron_request": false}}

Current date/time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

Only return the JSON, nothing else.'''

        try:
            ai_response = get_ai_response(prompt)
            json_match = re.search(r'\{.*\}', ai_response, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
            return {"is_cron_request": False}
        except Exception as e:
            logger.error(f"Error parsing cron request: {e}")
            return {"is_cron_request": False}

    def create_cron_from_natural_language(self, text, user_id, get_ai_response, schedule_job):
        parsed = self.parse_cron_from_text(text, get_ai_response)
        if not parsed.get("is_cron_request"):
            return None

        name = parsed.get("name") or f"job_{int(time.time())}"
        job_type = parsed.get("type", "send_message")
        schedule = parsed.get("schedule", "daily at 09:00")
        params = parsed.get("params") or {}

        if self._is_email_fetch_intent(text, job_type, params):
            job_type = "check_email"
            params = {}

        if job_type == "send_message" and "message" not in params:
            params["message"] = text
        if job_type in {"send_message", "check_email"}:
            params["user_id"] = user_id

        success, message = database.add_cron_job(name, job_type, schedule, params)
        if not success:
            return f"❌ Failed to create job: {message}"

        job = {'name': name, 'job_type': job_type, 'schedule': schedule, 'params': params, 'enabled': True}
        if schedule_job(job):
            job_emoji = "📬" if job_type == "send_message" else "⚙️" if job_type == "custom_command" else "📧"
            return f"""✅ *Cron Job Created Successfully!*

{job_emoji} *Job Details:*
• 📝 *Name:* `{name}`
• 🔧 *Type:* {job_type.replace('_', ' ').title()}
• ⏰ *Schedule:* {schedule}

💡 _Use /listjobs to view all your scheduled jobs_"""

        logger.warning(f"Job '{name}' created in DB but failed to schedule. Schedule: {schedule}")
        return "⚠️ Job saved but scheduling failed.\n\n**Possible issue:** Schedule format might be unsupported.\n\nUse /listjobs and recreate with simpler schedule."

    def manage_cron_job_nl(self, text, user_id, get_ai_response, schedule_job, scheduler):
        text_lower = text.lower().strip()

        if re.search(r'(?:list|show|view|display)\s+(?:all\s+)?(?:my\s+)?(?:cron\s+)?jobs?', text_lower):
            jobs = database.get_all_cron_jobs()
            if not jobs:
                return "📋 No cron jobs configured. Say something like 'remind me to check email every morning' to create one."

            result = "⏰ **Your Scheduled Jobs:**\n\n"
            for job in jobs:
                status = "✅ Active" if job['enabled'] else "❌ Paused"
                result += f"**{job['name']}** ({status})\n"
                result += f"  • Type: {job['job_type']}\n"
                result += f"  • Schedule: {job['schedule']}\n"
                if job['params']:
                    result += f"  • Details: {str(job['params'])[:50]}...\n"
                result += "\n"
            return result

        management_info = self.interpret_cron_management(text, user_id, get_ai_response)
        if not management_info or not management_info.get('action'):
            return None

        action = management_info.get('action')
        job_name = management_info.get('job_name')

        if action == 'delete':
            if database.remove_cron_job(job_name):
                try:
                    scheduler.remove_job(job_name)
                except Exception:
                    pass
                return f"✅ Deleted job '{job_name}' successfully."
            return f"❌ Job '{job_name}' not found."

        if action == 'enable':
            if database.toggle_cron_job(job_name, True):
                job = database.get_cron_job_by_name(job_name)
                if job:
                    schedule_job(job)
                return f"✅ Enabled job '{job_name}'."
            return f"❌ Job '{job_name}' not found."

        if action == 'disable':
            if database.toggle_cron_job(job_name, False):
                try:
                    scheduler.remove_job(job_name)
                except Exception:
                    pass
                return f"✅ Paused job '{job_name}'."
            return f"❌ Job '{job_name}' not found."

        if action == 'edit':
            new_schedule = management_info.get('new_schedule')
            new_params = management_info.get('new_params')
            success, msg = database.update_cron_job(job_name, schedule=new_schedule, params=new_params)
            if success:
                try:
                    scheduler.remove_job(job_name)
                except Exception:
                    pass
                job = database.get_cron_job_by_name(job_name)
                if job and job['enabled']:
                    schedule_job(job)
                return f"✅ Updated job '{job_name}' successfully!"
            return f"❌ {msg}"

        return None

    def interpret_cron_management(self, text, user_id, get_ai_response):
        jobs = database.get_all_cron_jobs()
        job_names = [job['name'] for job in jobs]

        prompt = f'''Analyze this cron job management request.

User message: "{text}"

Available job names: {', '.join(job_names) if job_names else 'none'}

Determine:
1. What action: delete, enable, disable, edit
2. Which job (match to existing names if possible)
3. If editing: new schedule and/or parameters

Return ONLY a JSON object:
{{
  "action": "delete|enable|disable|edit",
  "job_name": "exact_job_name",
  "new_schedule": "schedule if editing",
  "new_params": {{"key": "value"}} if editing
}}

Only return the JSON, nothing else.'''

        try:
            ai_response = get_ai_response(prompt, user_id)
            json_match = re.search(r'\{.*\}', ai_response, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
            return None
        except Exception as e:
            logger.error(f"Error interpreting cron management: {e}")
            return None
