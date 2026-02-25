import logging
import re
from datetime import datetime

import database


logger = logging.getLogger(__name__)


class TrackingService:
    def detect_tracking_request(self, text, user_id, get_ai_response):
        text_lower = text.lower().strip()

        weather_exclusions = [
            'weather', 'forecast', 'temperature', 'rain', 'sunny', 'cloud',
            'humidity', 'wind', 'detailed weather', 'weather report'
        ]
        if any(keyword in text_lower for keyword in weather_exclusions):
            return None

        sleep_result = self.detect_sleep_tracking(text, user_id)
        if sleep_result:
            return sleep_result

        report_patterns = [
            r'(?:give me|show me|generate|create)\s+(?:a\s+)?(.+?)\s+report',
            r'report\s+(?:on|about|for)\s+(?:my\s+)?(.+)',
            r'how\s+(?:much|many|often)\s+(?:did i|have i)\s+(.+)',
            r'(.+)\s+(?:statistics|stats|summary|analysis)',
        ]
        for pattern in report_patterns:
            if re.search(pattern, text_lower):
                report_info = self.interpret_report_request(text, user_id, get_ai_response)
                if report_info:
                    return self.generate_tracking_report(
                        user_id,
                        report_info.get('category'),
                        report_info.get('days', 7),
                    )

        tracking_keywords = [
            'track', 'log', 'record', 'note that', 'i did', 'i completed',
            'i studied', 'i exercised', 'i drank', 'i ate', 'my mood is',
            'feeling', 'worked out', 'practiced', 'meditated'
        ]
        has_tracking_keyword = any(keyword in text_lower for keyword in tracking_keywords)

        if has_tracking_keyword or 'remind me' in text_lower or 'report' in text_lower:
            tracking_info = self.interpret_tracking_request(text, user_id, get_ai_response)
            if tracking_info and tracking_info.get('should_track'):
                database.log_tracking_event(
                    user_id,
                    tracking_info.get('category'),
                    tracking_info.get('event_type'),
                    tracking_info.get('value'),
                    tracking_info.get('unit'),
                    tracking_info.get('notes')
                )

                category = tracking_info.get('category', '').title()
                value = tracking_info.get('value')
                unit = tracking_info.get('unit', '')
                response = (
                    f"✅ Got it! Tracked {value} {unit} of {category.lower()}."
                    if value else f"✅ Noted! {category} tracked."
                )

                schedule_info = tracking_info.get('schedule_report')
                if schedule_info and schedule_info.get('enabled'):
                    job_name = f"report_{tracking_info.get('category')}_{user_id}_{int(datetime.now().timestamp())}"
                    report_days = schedule_info.get('days', 7)
                    schedule_time = schedule_info.get('time', '09:00')
                    success, _ = database.add_cron_job(
                        job_name,
                        'send_message',
                        f'daily at {schedule_time}',
                        {
                            'user_id': user_id,
                            'message': f'TRACKING_REPORT:{user_id}:{tracking_info.get("category")}:{report_days}'
                        }
                    )
                    if success:
                        period = f"{report_days} days" if report_days != 7 else "a week"
                        response += f" I'll send you a report in {period}."

                return response

        return None

    def interpret_tracking_request(self, text, user_id, get_ai_response):
        prompt = f'''Analyze this user message and extract tracking information.

User message: "{text}"

Return ONLY a JSON object:
{{
  "should_track": true/false,
  "category": "exercise|study|mood|water|food|habit|etc",
  "event_type": "specific action taken",
  "value": numeric_value_or_null,
  "unit": "hours|minutes|cups|km|reps|etc",
  "notes": "any additional details",
  "schedule_report": {{
    "enabled": true/false,
    "days": 7,
    "time": "09:00"
  }}
}}

Only return the JSON, nothing else.'''

        try:
            ai_response = get_ai_response(prompt, user_id)
            json_match = re.search(r'\{.*\}', ai_response, re.DOTALL)
            if json_match:
                import json
                return json.loads(json_match.group())
            return None
        except Exception as e:
            logger.error(f"Error interpreting tracking request: {e}")
            return None

    def interpret_report_request(self, text, user_id, get_ai_response):
        prompt = f'''Analyze this report request and extract the details.

User message: "{text}"

Return ONLY a JSON object:
{{
  "category": "sleep|exercise|study|mood|water|etc",
  "days": 7
}}

Only return the JSON, nothing else.'''

        try:
            ai_response = get_ai_response(prompt, user_id)
            json_match = re.search(r'\{.*\}', ai_response, re.DOTALL)
            if json_match:
                import json
                return json.loads(json_match.group())
            return None
        except Exception as e:
            logger.error(f"Error interpreting report request: {e}")
            return None

    def generate_tracking_report(self, user_id, category, days=7):
        from datetime import datetime as dt

        tracking_data = database.get_tracking_data(user_id, category, days)
        if not tracking_data:
            categories = database.get_tracking_categories(user_id)
            if categories:
                return f"📊 No {category} data found for the last {days} days.\n\nAvailable categories: {', '.join(categories)}"
            return "📊 No tracking data found. Start tracking by telling me what you're doing!"

        events = []
        for cat, event_type, value, unit, notes, timestamp in tracking_data:
            events.append({
                'event_type': event_type,
                'value': value,
                'unit': unit,
                'notes': notes,
                'timestamp': dt.fromisoformat(timestamp)
            })

        report = f"📊 **{category.title()} Report - Last {days} Days**\n\n"
        report += f"📝 **Total Entries:** {len(events)}\n"

        values = [e['value'] for e in events if e['value'] is not None]
        if values:
            total = sum(values)
            avg = total / len(values)
            unit = events[0]['unit'] or ''
            report += f"📈 **Total:** {total:.1f} {unit}\n"
            report += f"📊 **Average:** {avg:.1f} {unit} per entry\n"
            report += f"🌟 **Highest:** {max(values):.1f} {unit}\n"
            report += f"📉 **Lowest:** {min(values):.1f} {unit}\n"

        event_types = {}
        for e in events:
            event_types[e['event_type']] = event_types.get(e['event_type'], 0) + 1
        if len(event_types) > 1:
            report += "\n📋 **Breakdown:**\n"
            for event, count in sorted(event_types.items(), key=lambda x: x[1], reverse=True):
                report += f"  • {event}: {count} times\n"

        report += "\n📅 **Recent Entries:**\n"
        for i, event in enumerate(reversed(events[-5:]), 1):
            date_str = event['timestamp'].strftime('%b %d, %I:%M %p')
            value_str = f"{event['value']} {event['unit']}" if event['value'] else ""
            notes_str = f" - {event['notes']}" if event['notes'] else ""
            report += f"{i}. {date_str}: {event['event_type']} {value_str}{notes_str}\n"

        report += "\n💡 **Tip:** Keep up the consistency! Track regularly to see better patterns.\n"
        return report

    def detect_sleep_tracking(self, text, user_id):
        text_lower = text.lower().strip()

        bedtime_patterns = [
            r'good night', r'going to (sleep|bed)', r'signing off',
            r'hitting the (sack|hay)', r'time to sleep', r'off to bed',
        ]
        for pattern in bedtime_patterns:
            if re.search(pattern, text_lower):
                database.log_sleep_event(user_id, 'bedtime')
                current_time = datetime.now().strftime("%I:%M %p")
                report_patterns = [r'after (a|1) week.*report', r'report.*week', r'weekly.*report', r'track.*sleep']
                should_schedule_report = any(re.search(p, text_lower) for p in report_patterns)
                if should_schedule_report:
                    job_name = f"sleep_report_{user_id}_{int(datetime.now().timestamp())}"
                    database.add_cron_job(
                        job_name,
                        'send_message',
                        f'daily at {current_time}',
                        {'user_id': user_id, 'message': f'SLEEP_REPORT:{user_id}:7'}
                    )
                    return f"🌙 Good night! The time is {current_time}. I'll track your sleep and send you a report in 7 days. Sweet dreams! 😴"
                return f"🌙 Good night! The time is {current_time}. Sleep tight! 😴"

        wakeup_patterns = [r'good morning', r'just woke up', r'waking up', r'rise and shine', r'wakey wakey']
        for pattern in wakeup_patterns:
            if re.search(pattern, text_lower):
                database.log_sleep_event(user_id, 'wake')
                current_time = datetime.now().strftime("%I:%M %p")
                sleep_data = database.get_sleep_data(user_id, days=1)
                if len(sleep_data) >= 2:
                    bedtime_entry = None
                    for event_type, timestamp, notes in reversed(sleep_data):
                        if event_type == 'bedtime':
                            bedtime_entry = timestamp
                            break
                    if bedtime_entry:
                        bedtime_dt = datetime.fromisoformat(bedtime_entry)
                        wake_dt = datetime.now()
                        hours = (wake_dt - bedtime_dt).total_seconds() / 3600
                        return f"☀️ Good morning! The time is {current_time}. You got about {hours:.1f} hours of sleep. Have a great day! 🌟"
                return f"☀️ Good morning! The time is {current_time}. Rise and shine! 🌟"

        if 'sleep report' in text_lower or 'how did i sleep' in text_lower or 'sleep analysis' in text_lower:
            days_match = re.search(r'(\d+)\s*days?', text_lower)
            days = int(days_match.group(1)) if days_match else 7
            return self.generate_sleep_report(user_id, days)

        return None

    def generate_sleep_report(self, user_id, days=7):
        sleep_data = database.get_sleep_data(user_id, days=days)
        if not sleep_data:
            return f"📊 No sleep data found for the last {days} days. Start tracking by saying 'good night' when you go to bed!"

        sessions = []
        current_bedtime = None
        for event_type, timestamp, notes in sleep_data:
            if event_type == 'bedtime':
                current_bedtime = datetime.fromisoformat(timestamp)
            elif event_type == 'wake' and current_bedtime:
                wake_time = datetime.fromisoformat(timestamp)
                duration = (wake_time - current_bedtime).total_seconds() / 3600
                sessions.append({'bedtime': current_bedtime, 'wake': wake_time, 'duration': duration})
                current_bedtime = None

        if not sessions:
            return "📊 No complete sleep sessions found. Make sure to log both 'good night' and 'good morning'!"

        total_nights = len(sessions)
        total_hours = sum(s['duration'] for s in sessions)
        avg_hours = total_hours / total_nights
        min_sleep = min(sessions, key=lambda x: x['duration'])
        max_sleep = max(sessions, key=lambda x: x['duration'])

        report = f"📊 **Sleep Report - Last {days} Days**\n\n"
        report += f"🛌 **Total Nights Tracked:** {total_nights}\n"
        report += f"⏱️ **Average Sleep:** {avg_hours:.1f} hours/night\n"
        report += f"📈 **Total Sleep Time:** {total_hours:.1f} hours\n"
        report += f"🌟 **Best Night:** {max_sleep['duration']:.1f} hours ({max_sleep['bedtime'].strftime('%b %d')})\n"
        report += f"⚠️ **Shortest Night:** {min_sleep['duration']:.1f} hours ({min_sleep['bedtime'].strftime('%b %d')})\n\n"

        if avg_hours >= 7:
            report += "✅ **Sleep Quality:** Good! You're getting recommended sleep.\n"
        elif avg_hours >= 6:
            report += "⚠️ **Sleep Quality:** Fair. Try to get more sleep.\n"
        else:
            report += "❌ **Sleep Quality:** Poor. You need more rest!\n"

        report += "\n📅 **Recent Sessions:**\n"
        for i, session in enumerate(reversed(sessions[-5:]), 1):
            date_str = session['bedtime'].strftime('%b %d')
            bed_time = session['bedtime'].strftime('%I:%M %p')
            wake_time = session['wake'].strftime('%I:%M %p')
            report += f"{i}. {date_str}: {bed_time} → {wake_time} ({session['duration']:.1f}h)\n"

        return report
