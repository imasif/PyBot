import json
import logging
import re

import database


logger = logging.getLogger(__name__)


class NotesService:
    def detect_request(self, text, user_id=None, check_learned_patterns=None, learn_from_interaction=None):
        text_lower = text.lower().strip()

        if user_id and check_learned_patterns:
            learned = check_learned_patterns(user_id, text_lower, 'notes')
            if learned:
                intent = learned['detected_intent']
                if intent.startswith('notes_create'):
                    return {'action': 'create', 'text': text}
                if intent == 'notes_list':
                    return {'action': 'list'}
                if intent.startswith('notes_search:'):
                    query = intent.split(':', 1)[1]
                    return {'action': 'search', 'query': query}

        create_patterns = [
            r'(?:create|make|add|write|save|take)(?: a| new)? note',
            r'note (?:this|that)',
            r'remember (?:this|that)',
        ]

        for pattern in create_patterns:
            if re.search(pattern, text_lower):
                result = {'action': 'create', 'text': text}
                if user_id and learn_from_interaction:
                    learn_from_interaction(user_id, text_lower, 'notes', 'notes_create')
                return result

        if re.search(r'(?:show|list|get|see|view)(?: my)? notes?', text_lower):
            result = {'action': 'list'}
            if user_id and learn_from_interaction:
                learn_from_interaction(user_id, text_lower, 'notes', 'notes_list')
            return result

        search_match = re.search(r'(?:search|find)(?: my)? notes? (?:for|about) (.+)', text_lower)
        if search_match:
            query = search_match.group(1).strip()
            result = {'action': 'search', 'query': query}
            if user_id and learn_from_interaction:
                learn_from_interaction(user_id, text_lower, 'notes', f'notes_search:{query}')
            return result

        return None

    def create_note(self, text, user_id, ask_ollama):
        prompt = f'''Extract the title and content from this note request:
"{text}"

Return ONLY a JSON object with this exact format:
{{"title": "extracted title", "content": "extracted content"}}

If the user didn't specify a title, create a short one from the content.
'''

        ai_response = ask_ollama(prompt, [])

        try:
            json_match = re.search(r'\{.*\}', ai_response, re.DOTALL)
            if json_match:
                note_data = json.loads(json_match.group())
                title = note_data.get('title', '').strip()
                content = note_data.get('content', '').strip()

                if content:
                    note_id = database.add_note(user_id, title or 'Untitled', content)
                    preview = content[:100] + ('...' if len(content) > 100 else '')
                    return f"✅ Note #{note_id} saved!\n\n**{title or 'Untitled'}**\n{preview}"
                return "❌ Could not extract note content. Please try again with more details."

            note_id = database.add_note(user_id, 'Quick Note', text)
            return f"✅ Note #{note_id} saved!"
        except Exception as e:
            logger.error(f"Note creation error: {e}")
            note_id = database.add_note(user_id, 'Quick Note', text)
            return f"✅ Note #{note_id} saved!"

    def list_notes(self, user_id):
        notes = database.get_notes(user_id, limit=10)

        if not notes:
            return "📝 You don't have any notes yet.\n\nTry: 'Create a note: Buy groceries tomorrow'"

        result = "📝 **Your Notes:**\n\n"
        for note_id, title, content, tags, created, updated in notes:
            preview = content[:50] + '...' if len(content) > 50 else content
            result += f"**#{note_id}** - {title}\n{preview}\n_{created[:10]}_\n\n"

        return result

    def search_notes(self, query, user_id):
        notes = database.search_notes(user_id, query)

        if not notes:
            return f"🔍 No notes found matching '{query}'"

        result = f"🔍 **Found {len(notes)} note(s) matching '{query}':**\n\n"
        for note_id, title, content, tags, created, updated in notes:
            preview = content[:100] + '...' if len(content) > 100 else content
            result += f"**#{note_id}** - {title}\n{preview}\n\n"

        return result

    def handle_interaction(
        self,
        text,
        user_id,
        nlu_intent=None,
        check_learned_patterns=None,
        learn_from_interaction=None,
        ask_ollama=None,
        **_kwargs,
    ):
        note_detection = self.detect_request(
            text,
            user_id=user_id,
            check_learned_patterns=check_learned_patterns,
            learn_from_interaction=learn_from_interaction,
        )
        if not note_detection:
            return None

        action = note_detection.get('action')
        if action == 'create':
            if not ask_ollama:
                reply = "❌ Notes service is not available right now."
            else:
                reply = self.create_note(text, user_id, ask_ollama)
        elif action == 'list':
            reply = self.list_notes(user_id)
        elif action == 'search':
            query = note_detection.get('query')
            reply = self.search_notes(query, user_id)
        else:
            reply = "❌ Unknown note action"

        return {'handled': True, 'reply': reply, 'parse_mode': 'HTML'}
