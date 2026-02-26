import logging
import re
from datetime import datetime

import database


logger = logging.getLogger(__name__)


def _sync_current_datetime(identity_text):
    if not identity_text:
        return identity_text

    now_str = datetime.now().strftime("%A, %B %d, %Y, %H:%M")
    pattern = r'(Current date and time\s*:\s*)([^\n\r]+)'
    return re.sub(pattern, rf'\1{now_str}', identity_text, flags=re.IGNORECASE)


class IdentityService:
    def process_identity_update(self, user_request, user_id, read_identity, ask_ollama):
        current_identity = read_identity()
        chat_history = None
        if user_id:
            chat_history = database.get_user_chat_history(user_id, limit=15)

        prompt = f'''Current bot identity:
{current_identity}

User wants to update the identity with this request: "{user_request}"

Please update the identity.md file content based on the user's request. Return ONLY the updated markdown content for identity.md file.

Guidelines:
- Keep the same markdown structure (# Bot Identity, ## sections)
- Modify only the relevant sections based on the request
- If they mention name, update ## Name section
- If they mention personality/traits, update those sections
- If they mention communication style, update that section
- Keep other sections unchanged unless user explicitly wants to change them
- Be clear and concise

Return the FULL updated identity.md content:'''

        try:
            updated_identity = ask_ollama(prompt, chat_history=chat_history)
            updated_identity = re.sub(r'^```(?:markdown)?\n', '', updated_identity, flags=re.MULTILINE)
            updated_identity = re.sub(r'\n```$', '', updated_identity, flags=re.MULTILINE)
            updated_identity = _sync_current_datetime(updated_identity)
            return updated_identity.strip()
        except Exception as e:
            logger.error(f"Error processing identity update: {e}")
            return None

    def interpret_identity_request(self, text):
        text_lower = text.lower()

        identity_patterns = [
            r'(?:change|update|edit|set|modify)\s+(?:your\s+)?(?:identity|personality|name|traits?|style)',
            r'(?:be|act)\s+(?:more\s+)?(?:professional|casual|friendly|formal|funny|serious)',
            r'(?:your\s+)?name\s+(?:is|should be)\s+(.+)',
            r'call\s+yourself\s+(.+)',
            r'identity\s*:\s*(.+)'
        ]

        for pattern in identity_patterns:
            if re.search(pattern, text_lower):
                return {"action": "update_identity", "text": text}

        if any(keyword in text_lower for keyword in [
            "show your identity", "what is your identity", "show identity", "read identity",
            "current identity", "your personality"
        ]):
            return {"action": "show_identity"}

        return None
