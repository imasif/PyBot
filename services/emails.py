import html as html_module
import imaplib
import json
import email
import re
from email.header import decode_header
import logging
from typing import Optional

import config
import database

logger = logging.getLogger(__name__)


URL_PATTERN = re.compile(r'https?://[^\s"<>]+')


def _escape_and_linkify(text: Optional[str], fallback: str = 'Unknown') -> str:
    if not text:
        return fallback
    decoded = html_module.unescape(text)
    decoded = decoded.strip()
    if not decoded:
        return fallback

    parts = []
    last_idx = 0
    for match in URL_PATTERN.finditer(decoded):
        parts.append(html_module.escape(decoded[last_idx:match.start()]))
        url = match.group(0)
        safe_url = html_module.escape(url)
        parts.append(f'<a href="{safe_url}">{safe_url}</a>')
        last_idx = match.end()
    parts.append(html_module.escape(decoded[last_idx:]))
    return ''.join(parts)


def _escape_body(text: Optional[str]) -> str:
    if not text:
        return ''
    decoded = html_module.unescape(text)
    decoded = decoded.strip()
    if not decoded:
        return ''

    parts = []
    last_idx = 0
    link_index = 0
    for match in URL_PATTERN.finditer(decoded):
        parts.append(html_module.escape(decoded[last_idx:match.start()]))
        url = match.group(0)
        safe_url = html_module.escape(url)
        link_index += 1
        parts.append(f'<a href="{safe_url}"><u>Link {link_index}</u></a>')
        last_idx = match.end()
    parts.append(html_module.escape(decoded[last_idx:]))
    return ''.join(parts)


def _strip_code_fences(value: str) -> str:
    cleaned = re.sub(r'```[\s\S]*?```', '', value or '')
    cleaned = re.sub(r'`([^`\n]+)`', r'\1', cleaned)
    return cleaned


def _html_to_text(value: str) -> str:
    cleaned = re.sub(r'<style[^>]*>.*?</style>', '', value, flags=re.IGNORECASE | re.DOTALL)
    cleaned = re.sub(r'<(br|p|div|li|tr|table)[^>]*>', '\n', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'<[^>]+>', '', cleaned)
    cleaned = html_module.unescape(cleaned)
    cleaned = re.sub(r'\n\s+', '\n', cleaned)
    cleaned = re.sub(r'\s+\n', '\n', cleaned)
    return cleaned.strip()


class EmailService:
    def __init__(self):
        self.imap_host = 'imap.gmail.com'
        self.username = config.GMAIL_EMAIL
        self.password = config.GMAIL_APP_PASSWORD

    def _connect(self) -> Optional[imaplib.IMAP4_SSL]:
        if not self.username or not self.password:
            logger.error("Email credentials missing")
            return None
        try:
            mail = imaplib.IMAP4_SSL(self.imap_host)
            mail.login(self.username, self.password)
            return mail
        except imaplib.IMAP4.error as e:
            logger.error(f"IMAP login error: {e}")
        except Exception as e:
            logger.error(f"Unexpected error connecting to IMAP: {e}")
        return None

    def _decode_subject(self, subject: Optional[str]) -> str:
        if not subject:
            return "No Subject"
        decoded_parts = decode_header(subject)
        subject_parts = []
        for part, encoding in decoded_parts:
            if isinstance(part, bytes):
                try:
                    subject_parts.append(part.decode(encoding or 'utf-8', errors='ignore'))
                except Exception:
                    subject_parts.append(part.decode('utf-8', errors='ignore'))
            else:
                subject_parts.append(str(part))
        return ''.join(subject_parts)

    def _fetch_messages(self, mail: imaplib.IMAP4_SSL, search_criterion: str, limit: int) -> list:
        mail.select('inbox')
        status, messages = mail.search(None, search_criterion)
        if status != 'OK':
            logger.error(f"IMAP search failed: {status}")
            return []
        email_ids = messages[0].split()
        if not email_ids:
            return []
        return email_ids[-limit:]

    def _build_email_summary(self, mail, email_ids, user_id=None) -> str:
        summary = ''
        fetched_map = {}
        for idx, email_id in enumerate(email_ids, 1):
            status, msg_data = mail.fetch(email_id, '(RFC822)')
            msg = email.message_from_bytes(msg_data[0][1])
            subject = _escape_and_linkify(self._decode_subject(msg['Subject']))
            from_email = _escape_and_linkify(msg.get('From', 'Unknown'))
            date = _escape_and_linkify(msg.get('Date', 'Unknown'))
            summary += f"[{idx}] ✉️ <b>From:</b> {from_email}\n"
            summary += f"    📅 <b>Date:</b> {date}\n"
            summary += f"    📝 <b>Subject:</b> {subject}\n\n"
            fetched_map[str(idx)] = email_id.decode() if isinstance(email_id, bytes) else str(email_id)

        if user_id and fetched_map:
            database.set_config(f"email_map_{user_id}", json.dumps(fetched_map))

        return summary

    def list_unread(self, limit=5, user_id=None) -> str:
        mail = self._connect()
        if not mail:
            return "Failed to connect to Gmail. Check credentials."
        try:
            email_ids = self._fetch_messages(mail, 'UNSEEN', limit)
            if not email_ids:
                return "No unread emails."
            summary = self._build_email_summary(mail, email_ids, user_id=user_id)
            return f"📧 You have {len(email_ids)} unread email(s):\n\n{summary}\n💡 Say 'read email 1' to view full content"
        finally:
            mail.logout()

    def list_recent(self, limit=5, user_id=None) -> str:
        mail = self._connect()
        if not mail:
            return "Failed to connect to Gmail. Check credentials."
        try:
            email_ids = self._fetch_messages(mail, 'ALL', limit)
            if not email_ids:
                return "No emails found."
            summary = self._build_email_summary(mail, email_ids, user_id=user_id)
            return f"📬 Recent {len(email_ids)} email(s):\n\n{summary}"
        finally:
            mail.logout()

    def search(self, query: str, limit=5, user_id=None) -> str:
        mail = self._connect()
        if not mail:
            return "Failed to connect to Gmail. Check credentials."
        try:
            search_query = f'(OR SUBJECT "{query}" FROM "{query}")'
            email_ids = self._fetch_messages(mail, search_query, limit)
            if not email_ids:
                return f"No emails found matching '{query}'."
            summary = self._build_email_summary(mail, email_ids, user_id=user_id)
            return f"🔍 Found {len(email_ids)} email(s) matching '{query}':\n\n{summary}"
        finally:
            mail.logout()

    def read_full(self, email_number: int, user_tag: str) -> str:
        mapping_json = database.get_config(f"email_map_{user_tag}")
        if not mapping_json:
            return "🔒 No recent email list found. Run 'show my unread emails' first."
        mapping = json.loads(mapping_json)
        email_id = mapping.get(str(email_number))
        if not email_id:
            return f"No entry for email {email_number}."
        mail = self._connect()
        if not mail:
            return "Failed to connect to Gmail. Check credentials."
        try:
            mail.select('inbox')
            status, msg_data = mail.fetch(email_id, '(RFC822)')
            msg = email.message_from_bytes(msg_data[0][1])
            subject = _escape_and_linkify(self._decode_subject(msg['Subject']))
            from_email = _escape_and_linkify(msg.get('From', 'Unknown'))
            to_email = _escape_and_linkify(msg.get('To', 'Unknown'))
            date = _escape_and_linkify(msg.get('Date', 'Unknown'))
            body = _escape_body(_strip_code_fences(self._extract_body(msg)))
            if not body:
                body = "(No readable text body found)"
            result = (
                f"📧 <b>Email #{email_number}</b>\n\n"
                f"✉️ <b>From:</b> {from_email}\n"
                f"📨 <b>To:</b> {to_email}\n"
                f"📅 <b>Date:</b> {date}\n"
                f"📝 <b>Subject:</b> {subject}\n\n"
                f"<b>Body:</b>\n{body}"
            )
            return result
        finally:
            mail.logout()

    def _extract_body(self, message: email.message.Message) -> str:
        plain_parts = []
        html_parts = []
        if message.is_multipart():
            for part in message.walk():
                content_type = (part.get_content_type() or '').lower()
                disposition = (part.get('Content-Disposition') or '').lower()
                if 'attachment' in disposition:
                    continue

                payload = part.get_payload(decode=True)
                if not payload:
                    continue

                charset = part.get_content_charset() or 'utf-8'
                try:
                    decoded = payload.decode(charset, errors='ignore')
                except Exception:
                    decoded = payload.decode(errors='ignore')

                if content_type == 'text/plain':
                    plain_parts.append(decoded)
                elif content_type == 'text/html':
                    html_parts.append(decoded)
        else:
            payload = message.get_payload(decode=True)
            if payload:
                charset = message.get_content_charset() or 'utf-8'
                try:
                    decoded = payload.decode(charset, errors='ignore')
                except Exception:
                    decoded = payload.decode(errors='ignore')

                content_type = (message.get_content_type() or '').lower()
                if content_type == 'text/html':
                    html_parts.append(decoded)
                else:
                    plain_parts.append(decoded)

        if plain_parts:
            return '\n'.join(plain_parts).strip()

        if html_parts:
            return _html_to_text('\n'.join(html_parts))

        return ''


MAX_EMAIL_LIMIT = 20
DEFAULT_EMAIL_LIMIT = 5
HELP_TEXT = (
    "Usage:\n"
    "/email recent [count] - list recent messages\n"
    "/email unread [count] - show unread messages\n"
    "/email search <query> - search your inbox\n"
    "/email read <number> - read a numbered email from the latest list"
)


def _parse_limit_arg(args, default=DEFAULT_EMAIL_LIMIT):
    if not args:
        return default
    try:
        value = int(args[0])
        return max(1, min(value, MAX_EMAIL_LIMIT))
    except ValueError:
        return default


def _service_missing_response() -> str:
    return "Email service is not available right now. Restart the bot so it can initialize."


def email_command_help() -> str:
    return HELP_TEXT


def handle_email_action(action: str, args: list[str], service: EmailService | None, user_id: str) -> str:
    if service is None:
        return _service_missing_response()

    action = action.lower()
    rest = args or []
    try:
        if action in ["recent", "latest", "list", "show"]:
            limit = _parse_limit_arg(rest)
            return service.list_recent(limit=limit, user_id=user_id)

        if action in ["unread", "new"]:
            limit = _parse_limit_arg(rest)
            return service.list_unread(limit=limit, user_id=user_id)

        if action == "search":
            query = " ".join(rest).strip()
            if not query:
                return "🔍 Please provide search keywords (e.g., /email search invoice)"
            return service.search(query=query, limit=_parse_limit_arg(rest, default=DEFAULT_EMAIL_LIMIT))

        if action == "read":
            if not rest:
                return "📖 Provide the email number to read. Example: /email read 2"
            try:
                email_number = int(rest[0])
            except ValueError:
                return "📖 Email number must be numeric."
            return service.read_full(email_number, user_tag=user_id)

        return "❓ Unknown /email subcommand. Use /email recent, /email unread, /email search, or /email read <number>."
    except Exception as exc:
        logger.error("Email command failed: %s", exc)
        return f"⚠️ Email command failed: {exc}"


def handle_email_request(request: dict, service: EmailService | None, user_id: str) -> str:
    if service is None:
        return _service_missing_response()

    action = request.get("action")
    params = request.get("params", {}) or {}

    try:
        if action == "recent":
            limit = min(int(params.get("limit", DEFAULT_EMAIL_LIMIT)), MAX_EMAIL_LIMIT)
            return service.list_recent(limit=limit, user_id=user_id)
        if action == "unread":
            limit = min(int(params.get("limit", DEFAULT_EMAIL_LIMIT)), MAX_EMAIL_LIMIT)
            return service.list_unread(limit=limit, user_id=user_id)
        if action == "search":
            query = params.get("query", "").strip()
            if not query:
                return "🔍 Please provide a search query."
            return service.search(query=query, limit=min(int(params.get("limit", DEFAULT_EMAIL_LIMIT)), MAX_EMAIL_LIMIT))
    except Exception as exc:
        logger.error("Email request handler error: %s", exc)
        return f"⚠️ Email request failed: {exc}"

    return "❓ Unable to understand that email request."


def handle_read_email(email_number: int, service: EmailService | None, user_id: str) -> str:
    if service is None:
        return _service_missing_response()
    try:
        return service.read_full(email_number, user_tag=user_id)
    except Exception as exc:
        logger.error("Read email failed: %s", exc)
        return f"⚠️ Unable to read email {email_number}: {exc}"


def interpret_email_request(text: str):
    text_lower = text.lower()
    unread_keywords = ["unread email", "new email", "check my email", "any new email",
                      "unread message", "new message", "emails i haven't read"]
    if any(keyword in text_lower for keyword in unread_keywords):
        return {"action": "unread", "params": {}}

    recent_patterns = [
        r"(?:read|show|check|get|fetch|see|display)\s+(?:my\s+)?(?:last|recent|latest)\s+(\d+)\s+emails?",
        r"last\s+(\d+)\s+emails?",
        r"recent\s+(\d+)\s+emails?",
        r"show\s+(?:me\s+)?(\d+)\s+emails?",
        r"(\d+)\s+recent\s+emails?",
        r"(\d+)\s+last\s+emails?",
        r"latest\s+(\d+)\s+emails?",
        r"(\d+)\s+emails?\s+(?:from|in)\s+(?:my\s+)?inbox"
    ]
    for pattern in recent_patterns:
        match = re.search(pattern, text_lower)
        if match:
            count = int(match.group(1))
            return {"action": "recent", "params": {"limit": min(count, MAX_EMAIL_LIMIT)}}

    recent_keywords = ["recent email", "latest email", "last email", "show my email",
                      "check email", "my email", "email list", "inbox", "read my email",
                      "show email", "get my email"]
    if any(keyword in text_lower for keyword in recent_keywords):
        return {"action": "recent", "params": {"limit": DEFAULT_EMAIL_LIMIT}}

    search_patterns = [
        r"search (?:for |my )?email(?:s)? (?:about |for |with )?(.+)",
        r"find email(?:s)? (?:about |with |from )?(.+)",
        r"email(?:s)? (?:about |containing |with )(.+)",
        r"look for email(?:s)? (.+)"
    ]
    for pattern in search_patterns:
        match = re.search(pattern, text_lower)
        if match:
            query = match.group(1).strip()
            query = re.sub(r"\s+(please|plz|pls)$", "", query)
            return {"action": "search", "params": {"query": query}}

    return None


def interpret_read_email_request(text: str):
    text_lower = text.lower()
    read_patterns = [
        r"(?:read|show|open|view|display|get)\s+email\s+(?:number\s+)?(\d+)",
        r"email\s+(\d+)",
        r"(?:number\s+)?(\d+)(?:\s+email)?$"
    ]
    for pattern in read_patterns:
        match = re.search(pattern, text_lower)
        if match:
            return int(match.group(1))
    return None
