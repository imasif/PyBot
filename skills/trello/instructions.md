# Trello Skill

**Purpose:** Manage Trello boards, lists, and cards through the Trello REST API.

**Triggers:** Use this skill when the user asks to view boards/lists/cards or create/move/archive Trello cards.

**Supported actions:**
- `list_boards`: return the authenticated user's boards.
- `list_lists`: return lists in a given board.
- `list_cards`: return cards in a given list.
- `create_card`: create a new card in a target list.
- `move_card`: move a card to another list.
- `archive_card`: archive (close) a card.

**Guidelines:**
- Ask for missing IDs (board ID, list ID, or card ID) before write actions.
- Confirm successful mutations (create/move/archive) with card name and destination.
- If Trello credentials are missing, instruct the user to set `TRELLO_API_KEY` and `TRELLO_TOKEN`.
- Keep responses concise and action-oriented.
