import re
from datetime import datetime
from typing import Any, Callable, Dict, Optional

import requests

import config


class TrelloService:
    BASE_URL = "https://api.trello.com/1"
    TIMEOUT = 20

    def __init__(self):
        self.api_key = (getattr(config, "TRELLO_API_KEY", "") or "").strip()
        self.token = (getattr(config, "TRELLO_TOKEN", "") or "").strip()
        self.session = requests.Session()

    @staticmethod
    def _looks_like_placeholder(value: str) -> bool:
        lowered = (value or "").strip().lower()
        if not lowered:
            return True
        return lowered.startswith("your_") or lowered.endswith("_here")

    def _credentials_ready(self) -> bool:
        return not self._looks_like_placeholder(self.api_key) and not self._looks_like_placeholder(self.token)

    def _request(self, method: str, path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if not self._credentials_ready():
            return {
                "ok": False,
                "error": "Trello is not configured. Set real TRELLO_API_KEY and TRELLO_TOKEN values in .env (not placeholder text) and restart the bot.",
            }

        all_params = {"key": self.api_key, "token": self.token}
        if params:
            all_params.update(params)

        url = f"{self.BASE_URL}/{path.lstrip('/')}"
        try:
            response = self.session.request(
                method=method.upper(),
                url=url,
                params=all_params,
                timeout=self.TIMEOUT,
            )
        except requests.RequestException as exc:
            return {"ok": False, "error": f"Trello request failed: {exc}"}

        try:
            payload = response.json() if response.content else {}
        except ValueError:
            payload = {"raw": response.text}

        if not response.ok:
            message = payload.get("message") if isinstance(payload, dict) else None
            if response.status_code == 401:
                message = message or "Unauthorized. Trello key/token is invalid, expired, or does not match account permissions."
            return {
                "ok": False,
                "status": response.status_code,
                "error": message or f"Trello API error ({response.status_code})",
                "data": payload,
            }

        return {"ok": True, "data": payload}

    def list_boards(self) -> Dict[str, Any]:
        return self._request("GET", "members/me/boards", params={"fields": "id,name,url,closed"})

    def list_lists(self, board_id: str) -> Dict[str, Any]:
        return self._request(
            "GET",
            f"boards/{board_id}/lists",
            params={"fields": "id,name,closed,pos"},
        )

    def list_cards(self, list_id: str) -> Dict[str, Any]:
        return self._request(
            "GET",
            f"lists/{list_id}/cards",
            params={"fields": "id,name,desc,due,url,idList,closed"},
        )

    def create_card(self, list_id: str, name: str, desc: str = "", due: Optional[str] = None) -> Dict[str, Any]:
        params: Dict[str, Any] = {"idList": list_id, "name": name}
        if desc:
            params["desc"] = desc
        if due:
            params["due"] = due
        return self._request("POST", "cards", params=params)

    def move_card(self, card_id: str, target_list_id: str, pos: str = "top") -> Dict[str, Any]:
        return self._request(
            "PUT",
            f"cards/{card_id}",
            params={"idList": target_list_id, "pos": pos},
        )

    def archive_card(self, card_id: str) -> Dict[str, Any]:
        return self._request("PUT", f"cards/{card_id}", params={"closed": "true"})

    @staticmethod
    def _normalize_text(value: Optional[str]) -> str:
        cleaned = (value or "").strip().lower()
        return re.sub(r"[^a-z0-9]+", "", cleaned)

    @staticmethod
    def _extract_board_short_id(text: str) -> Optional[str]:
        match = re.search(r"trello\.com/b/([A-Za-z0-9]+)/", text or "", re.IGNORECASE)
        return match.group(1) if match else None

    def detect_request(self, text: str) -> Optional[Dict[str, Any]]:
        text_lower = (text or "").lower().strip()
        if not text_lower:
            return None

        has_trello_context = "trello" in text_lower or "trello.com/b/" in text_lower
        has_card_context = "card" in text_lower
        if not has_trello_context and not has_card_context:
            return None

        board_short_id = self._extract_board_short_id(text)

        if re.search(r"\b(card\s+url|url\s+of\s+(?:the\s+)?card|give\s+me\s+card\s+url)\b", text_lower):
            return {"action": "last_card_url", "board_short_id": board_short_id}

        if re.search(r"\b(move|shift)\b", text_lower) and "card" in text_lower:
            card_id = None
            card_match = re.search(r"trello\.com/c/([A-Za-z0-9]+)", text or "", re.IGNORECASE)
            if card_match:
                card_id = card_match.group(1)

            list_name = None
            list_match = re.search(r'(?:under|in|to)\s+["\']?([^"\'\n:]+?)["\']?\s+lists?', text or "", re.IGNORECASE)
            if list_match:
                list_name = list_match.group(1).strip()

            return {
                "action": "move_card",
                "card_id": card_id,
                "list_name": list_name,
                "board_short_id": board_short_id,
            }

        if re.search(r"\b(create|add|make)\b", text_lower) and "card" in text_lower:
            title = None
            quoted = re.search(r'"([^"]{2,200})"', text or "")
            if quoted:
                title = quoted.group(1).strip()

            if not title:
                name_match = re.search(r"(?:named|name)\s+(.+?)(?:\s+(?:under|in|to)\s+|$)", text or "", re.IGNORECASE)
                if name_match:
                    title = name_match.group(1).strip(" :.-")

            list_name = None
            list_match = re.search(r'(?:under|in|to)\s+["\']?([^"\'\n:]+?)["\']?\s+list', text or "", re.IGNORECASE)
            if list_match:
                list_name = list_match.group(1).strip()

            any_list = bool(re.search(r"\bany\s+list\b", text_lower))
            any_name = bool(re.search(r"\bany\s+name\b", text_lower))
            if not title and any_name:
                title = f"Task {datetime.now().strftime('%H:%M:%S')}"

            return {
                "action": "create_card",
                "title": title,
                "list_name": list_name,
                "any_list": any_list,
                "board_short_id": board_short_id,
            }

        if board_short_id and re.search(r"\b(access|overview|show|check|this\s+board)\b", text_lower):
            return {"action": "board_overview", "board_short_id": board_short_id}

        if has_trello_context:
            return {"action": "board_overview", "board_short_id": board_short_id}

        return None

    def _resolve_board(
        self,
        user_id: str,
        board_short_id: Optional[str],
        get_user_context: Callable[[str, str], Optional[str]],
        save_user_context: Callable[[str, str, str], None],
    ) -> tuple[Optional[Dict[str, Any]], Optional[str]]:
        boards_result = self.list_boards()
        if not boards_result.get("ok"):
            return None, f"❌ {boards_result.get('error', 'Failed to fetch Trello boards.')}"

        boards = boards_result.get("data") or []
        open_boards = [board for board in boards if not board.get("closed")]
        if not open_boards:
            return None, "❌ No open Trello boards found."

        effective_short_id = board_short_id or get_user_context(user_id, "last_trello_board_short_id")
        if effective_short_id:
            for board in open_boards:
                board_url = (board.get("url") or "").lower()
                if f"/b/{str(effective_short_id).lower()}/" in board_url:
                    save_user_context(user_id, "last_trello_board_short_id", str(effective_short_id))
                    return board, None

        selected = open_boards[0]
        selected_short = self._extract_board_short_id(selected.get("url", ""))
        if selected_short:
            save_user_context(user_id, "last_trello_board_short_id", selected_short)
        return selected, None

    def _find_list(self, lists_data: list, target_name: Optional[str], any_list: bool) -> Optional[Dict[str, Any]]:
        open_lists = [item for item in (lists_data or []) if not item.get("closed")]
        if not open_lists:
            return None

        if any_list or not target_name:
            return open_lists[0]

        normalized_target = self._normalize_text(target_name)
        aliases = {normalized_target}
        if normalized_target in {"todo", "todolist"}:
            aliases.update({"todo", "todolist"})

        for item in open_lists:
            normalized_name = self._normalize_text(item.get("name"))
            if normalized_name in aliases:
                return item

        for item in open_lists:
            normalized_name = self._normalize_text(item.get("name"))
            if normalized_target and (normalized_target in normalized_name or normalized_name in normalized_target):
                return item

        return None

    def handle_request(
        self,
        request: Dict[str, Any],
        user_id: str,
        get_user_context: Callable[[str, str], Optional[str]],
        save_user_context: Callable[[str, str, str], None],
    ) -> str:
        action = request.get("action")

        board, board_error = self._resolve_board(
            user_id,
            request.get("board_short_id"),
            get_user_context,
            save_user_context,
        )
        if board_error:
            return board_error

        if action == "last_card_url":
            last_url = get_user_context(user_id, "last_trello_card_url")
            if last_url:
                return f"🔗 Latest Trello card URL:\n{last_url}"
            return "❌ I don't have a recent Trello card URL yet. Create a card first."

        lists_result = self.list_lists(board.get("id"))
        if not lists_result.get("ok"):
            return f"❌ {lists_result.get('error', 'Failed to fetch board lists.')}"
        lists_data = lists_result.get("data") or []

        if action == "board_overview":
            list_names = [item.get("name", "Unnamed") for item in lists_data if not item.get("closed")]
            if not list_names:
                return f"📋 Board: {board.get('name')}\nNo open lists found."
            preview = "\n".join([f"• {name}" for name in list_names[:10]])
            return (
                f"📋 Board: {board.get('name')}\n"
                f"🔗 {board.get('url')}\n"
                f"Open lists ({len(list_names)}):\n{preview}"
            )

        if action == "create_card":
            title = (request.get("title") or "").strip()
            if not title:
                return "❌ Please provide a card name. Example: create card named \"Fix login\" under To Do list"

            target_list = self._find_list(
                lists_data,
                target_name=request.get("list_name"),
                any_list=bool(request.get("any_list")),
            )
            if not target_list:
                return "❌ Could not find the requested Trello list."

            create_result = self.create_card(target_list.get("id"), title)
            if not create_result.get("ok"):
                return f"❌ {create_result.get('error', 'Failed to create Trello card.')}"

            card = create_result.get("data") or {}
            card_url = card.get("url")
            if card_url:
                save_user_context(user_id, "last_trello_card_url", card_url)

            return (
                f"✅ Created Trello card: {card.get('name', title)}\n"
                f"📂 List: {target_list.get('name', 'Unknown')}\n"
                f"🔗 URL: {card_url or 'Unavailable'}"
            )

        if action == "move_card":
            card_id = (request.get("card_id") or "").strip()
            if not card_id:
                return "❌ Please provide a Trello card URL or card ID to move."

            target_list = self._find_list(
                lists_data,
                target_name=request.get("list_name"),
                any_list=False,
            )
            if not target_list:
                return "❌ Could not find the target Trello list for move."

            move_result = self.move_card(card_id, target_list.get("id"))
            if not move_result.get("ok"):
                return f"❌ {move_result.get('error', 'Failed to move Trello card.')}"

            moved_card = move_result.get("data") or {}
            moved_url = moved_card.get("url")
            if moved_url:
                save_user_context(user_id, "last_trello_card_url", moved_url)

            return (
                f"✅ Moved Trello card: {moved_card.get('name', card_id)}\n"
                f"📂 New list: {target_list.get('name', 'Unknown')}\n"
                f"🔗 URL: {moved_url or 'Unavailable'}"
            )

        return "❌ Unsupported Trello action."
