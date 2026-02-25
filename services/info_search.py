import logging
import re

import wikipediaapi
from duckduckgo_search import DDGS


logger = logging.getLogger(__name__)


class InfoSearchService:
    def detect_search_request(self, text, user_id=None, check_learned_patterns=None, learn_from_interaction=None):
        text_lower = text.lower().strip()

        time_date_exclusions = [
            'time', 'the time', 'current time', 'time now',
            'date', 'the date', 'current date', 'today', "today's date",
            'day', 'the day', 'what day',
        ]

        identity_exclusions = [
            'your name', 'your identity', 'who are you', 'who is this',
            'what are you', 'what is this bot', 'about you', 'about yourself',
            'what can you do', 'what do you do', 'your capabilities',
            'what you can do', 'help', 'your features', 'your purpose',
        ]

        for exclusion in time_date_exclusions:
            if text_lower in [
                f'what is {exclusion}', f"what's {exclusion}",
                f'what is the {exclusion}', f"what's the {exclusion}",
                f'tell me {exclusion}', f'show me {exclusion}',
                exclusion, f'the {exclusion}'
            ]:
                return None

        for exclusion in identity_exclusions:
            if exclusion in text_lower or text_lower in [
                f'what is {exclusion}', f"what's {exclusion}",
                f'tell me {exclusion}', f'who is {exclusion}'
            ]:
                return None

        if user_id and check_learned_patterns:
            learned = check_learned_patterns(user_id, text_lower, 'search')
            if learned and learned.startswith('search:'):
                query = learned.split(':', 1)[1]
                return {'action': 'search', 'query': query}

        search_patterns = [
            r'(?:search|google|look up|find) (?:for |about )?(.+)',
            r'what (?:is|are) (.+?)(?:\?|$)',
            r'who (?:is|are|was|were) (.+?)(?:\?|$)',
            r'where (?:is|are) (.+?)(?:\?|$)',
            r'when (?:is|was|did) (.+?)(?:\?|$)',
            r'how (?:to|do|does|did) (.+?)(?:\?|$)',
            r'why (?:is|are|do|does|did) (.+?)(?:\?|$)',
        ]

        for pattern in search_patterns:
            match = re.search(pattern, text_lower)
            if match:
                query = match.group(1).strip()
                if query in time_date_exclusions:
                    return None
                if len(query) > 3:
                    result = {'action': 'search', 'query': query}
                    if user_id and learn_from_interaction:
                        learn_from_interaction(user_id, text_lower, 'search', f'search:{query}')
                    return result

        return None

    def search_web(self, query):
        try:
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=5))

            if not results:
                return f"🔍 No results found for '{query}'"

            response = f"🔍 **Search results for '{query}':**\n\n"
            for i, result in enumerate(results[:3], 1):
                title = result.get('title', 'No title')
                snippet = result.get('body', 'No description')
                url = result.get('href', '')
                response += f"**{i}. {title}**\n{snippet[:150]}...\n{url}\n\n"

            return response
        except Exception as e:
            logger.error(f"Web search error: {e}")
            return "❌ Search error. Try asking me to search for something else."

    def detect_wikipedia_request(self, text, user_id=None, check_learned_patterns=None, learn_from_interaction=None):
        text_lower = text.lower().strip()

        identity_exclusions = [
            'your name', 'your identity', 'you', 'yourself',
            'this bot', 'about you', 'what can you do',
            'what do you do', 'your capabilities', 'help',
        ]

        for exclusion in identity_exclusions:
            if exclusion in text_lower:
                return None

        if user_id and check_learned_patterns:
            learned = check_learned_patterns(user_id, text_lower, 'wikipedia')
            if learned and learned.startswith('wiki:'):
                query = learned.split(':', 1)[1]
                return {'action': 'wiki', 'query': query}

        wiki_patterns = [
            r'wikipedia (?:for |about )?(.+)',
            r'tell me about (.+)',
            r'(?:what|who) (?:is|are|was|were) (.+?)(?:\?|$)',
        ]

        for pattern in wiki_patterns:
            match = re.search(pattern, text_lower)
            if match:
                query = match.group(1).strip()
                if any(excl in query for excl in identity_exclusions):
                    return None
                result = {'action': 'wiki', 'query': query}
                if user_id and learn_from_interaction:
                    learn_from_interaction(user_id, text_lower, 'wikipedia', f'wiki:{query}')
                return result

        return None

    def search_wikipedia(self, query):
        try:
            wiki = wikipediaapi.Wikipedia('JarvisBot/1.0', 'en')
            page = wiki.page(query)

            if not page.exists():
                return f"📚 No Wikipedia article found for '{query}'.\n\nTry searching the web instead."

            summary = page.summary[:500]
            if len(page.summary) > 500:
                summary += "..."

            return f"📚 **{page.title}**\n\n{summary}\n\n_Source: Wikipedia_"
        except Exception as e:
            logger.error(f"Wikipedia search error: {e}")
            return f"❌ Could not fetch Wikipedia article for '{query}'"
