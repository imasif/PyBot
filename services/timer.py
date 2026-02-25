import re
from datetime import datetime

import database


class TimerService:
    def detect_request(self, text, user_id=None, check_learned_patterns=None, learn_from_interaction=None):
        text_lower = text.lower().strip()

        if user_id and check_learned_patterns:
            learned = check_learned_patterns(user_id, text_lower, 'timer')
            if learned:
                intent = learned
                if intent.startswith('timer_create:'):
                    duration_text = intent.split(':', 1)[1]
                    return {'action': 'create', 'duration': duration_text}
                if intent == 'timer_list':
                    return {'action': 'list'}

        timer_patterns = [
            r'(?:set|start)(?: a)? timer (?:for )?(.+)',
            r'timer (?:for )?(.+)',
            r'countdown (?:for )?(.+)',
        ]

        for pattern in timer_patterns:
            match = re.search(pattern, text_lower)
            if match:
                duration_text = match.group(1).strip()
                result = {'action': 'create', 'duration': duration_text}
                if user_id and learn_from_interaction:
                    learn_from_interaction(user_id, text_lower, 'timer', f'timer_create:{duration_text}')
                return result

        if re.search(r'(?:show|list|my)(?: my)? timers?', text_lower):
            result = {'action': 'list'}
            if user_id and learn_from_interaction:
                learn_from_interaction(user_id, text_lower, 'timer', 'timer_list')
            return result

        return None

    def create_timer(self, duration_text, user_id):
        total_seconds = 0
        name = 'Timer'

        hours_match = re.search(r'(\d+)\s*(?:hour|hr|h)s?', duration_text)
        if hours_match:
            total_seconds += int(hours_match.group(1)) * 3600

        minutes_match = re.search(r'(\d+)\s*(?:minute|min|m)s?', duration_text)
        if minutes_match:
            total_seconds += int(minutes_match.group(1)) * 60

        seconds_match = re.search(r'(\d+)\s*(?:second|sec|s)s?', duration_text)
        if seconds_match:
            total_seconds += int(seconds_match.group(1))

        if total_seconds == 0:
            number_match = re.search(r'(\d+)', duration_text)
            if number_match:
                total_seconds = int(number_match.group(1)) * 60
                name = f"{number_match.group(1)} min timer"

        if total_seconds == 0:
            return "❌ Could not parse timer duration. Try: 'Set timer for 10 minutes' or 'Timer for 1 hour 30 min'"

        timer_id = database.add_timer(user_id, name, total_seconds)

        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60

        duration_str = ''
        if hours > 0:
            duration_str += f"{hours}h "
        if minutes > 0:
            duration_str += f"{minutes}m "
        if seconds > 0:
            duration_str += f"{seconds}s"

        return f"⏱️ Timer #{timer_id} started!\n\n**Duration:** {duration_str.strip()}\n\n_I'll notify you when it's done!_"

    def list_timers(self, user_id):
        timers = database.get_active_timers(user_id)

        if not timers:
            return "⏱️ No active timers.\n\nTry: 'Set timer for 10 minutes'"

        result = "⏱️ **Active Timers:**\n\n"
        for timer_id, name, duration_seconds, started_at, ends_at in timers:
            ends_dt = datetime.fromisoformat(ends_at)
            now = datetime.now()
            remaining = (ends_dt - now).total_seconds()

            if remaining > 0:
                hours = int(remaining // 3600)
                minutes = int((remaining % 3600) // 60)
                seconds = int(remaining % 60)

                time_str = ''
                if hours > 0:
                    time_str += f"{hours}h "
                if minutes > 0:
                    time_str += f"{minutes}m "
                if seconds > 0:
                    time_str += f"{seconds}s"

                result += f"**#{timer_id}** - {name}\n⏳ {time_str.strip()} remaining\n\n"
            else:
                result += f"**#{timer_id}** - {name}\n✅ Completed!\n\n"
                database.complete_timer(timer_id)

        return result
