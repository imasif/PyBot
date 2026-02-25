import re

import database


class ShoppingService:
    def detect_request(self, text, user_id=None, check_learned_patterns=None, learn_from_interaction=None):
        text_lower = text.lower().strip()

        if user_id and check_learned_patterns:
            learned = check_learned_patterns(user_id, text_lower, 'shopping')
            if learned:
                intent = learned['detected_intent']
                if intent.startswith('shopping_add:'):
                    items_text = intent.split(':', 1)[1]
                    return {'action': 'add', 'items': items_text}
                if intent == 'shopping_list':
                    return {'action': 'list'}
                if intent == 'shopping_clear':
                    return {'action': 'clear'}

        add_patterns = [
            r'add (.+) to (?:my )?shopping list',
            r'(?:put|add) (.+) (?:on|in) (?:the |my )?(?:shopping )?list',
            r'shopping list:? (.+)',
            r'buy (.+)',
        ]

        for pattern in add_patterns:
            match = re.search(pattern, text_lower)
            if match:
                items_text = match.group(1).strip()
                result = {'action': 'add', 'items': items_text}
                if user_id and learn_from_interaction:
                    learn_from_interaction(user_id, text_lower, 'shopping', f'shopping_add:{items_text}')
                return result

        if re.search(r"(?:show|list|view|get|see|what\\'s (?:on|in))(?: my)? shopping list", text_lower):
            result = {'action': 'list'}
            if user_id and learn_from_interaction:
                learn_from_interaction(user_id, text_lower, 'shopping', 'shopping_list')
            return result

        if re.search(r'clear(?: my)? shopping list', text_lower):
            result = {'action': 'clear'}
            if user_id and learn_from_interaction:
                learn_from_interaction(user_id, text_lower, 'shopping', 'shopping_clear')
            return result

        return None

    def add_items(self, items_text, user_id):
        items = re.split(r',|and|;|\n', items_text)
        items = [item.strip() for item in items if item.strip()]

        added = []
        for item in items:
            qty_match = re.match(r'(\d+)\s+(.+)', item)
            if qty_match:
                quantity = qty_match.group(1)
                item_name = qty_match.group(2)
            else:
                quantity = None
                item_name = item

            database.add_shopping_item(user_id, item_name, quantity)
            added.append(f"• {quantity + ' ' if quantity else ''}{item_name}")

        if added:
            return "🛒 Added to shopping list:\n\n" + "\n".join(added)
        return "❌ No items could be added. Try: 'Add milk and bread to shopping list'"

    def list_items(self, user_id):
        items = database.get_shopping_list(user_id)

        if not items:
            return "🛒 Your shopping list is empty.\n\nTry: 'Add milk to shopping list'"

        result = "🛒 **Shopping List:**\n\n"
        for item_id, item_name, quantity, is_purchased, created_at in items:
            qty_str = f"{quantity} " if quantity else ""
            result += f"**#{item_id}** {qty_str}{item_name}\n"

        result += f"\n_Total: {len(items)} item(s)_"
        return result

    def clear_items(self, user_id):
        deleted = database.clear_purchased_items(user_id)
        return f"🛒 Cleared {deleted} purchased item(s) from shopping list."
