import logging
import re

from newsapi import NewsApiClient


logger = logging.getLogger(__name__)


class NewsService:
    def detect_request(self, text, user_id=None, check_learned_patterns=None, learn_from_interaction=None):
        text_lower = text.lower().strip()

        if user_id and check_learned_patterns:
            learned = check_learned_patterns(user_id, text_lower, 'news')
            if learned:
                intent = learned
                if intent.startswith('news:'):
                    topic = intent.split(':', 1)[1]
                    return {'action': 'news', 'topic': topic if topic != 'None' else None}
                if intent == 'news':
                    return {'action': 'news', 'topic': None}

        news_patterns = [
            r'(?:get|show|tell me|read|fetch)(?: me)?(?: the)? news',
            r"(?:what\'s|what is|whats)(?: the)? (?:latest )?news",
            r'news (?:about|on|for) (.+)',
            r'headlines',
            r'(?:top |latest )?news (?:today|now)?',
        ]

        for pattern in news_patterns:
            match = re.search(pattern, text_lower)
            if match:
                topic_match = re.search(r'news (?:about|on|for) (.+)', text_lower)
                if topic_match:
                    topic = topic_match.group(1).strip()
                    result = {'action': 'news', 'topic': topic}
                    if user_id and learn_from_interaction:
                        learn_from_interaction(user_id, text_lower, 'news', f'news:{topic}')
                else:
                    result = {'action': 'news', 'topic': None}
                    if user_id and learn_from_interaction:
                        learn_from_interaction(user_id, text_lower, 'news', 'news')
                return result

        return None

    def get_news(self, api_key, topic=None, limit=5):
        if not api_key:
            return "❌ News service not configured. Please add NEWSAPI_KEY to .env file.\nGet your free API key at: https://newsapi.org/"

        try:
            newsapi = NewsApiClient(api_key=api_key)

            if topic:
                articles = newsapi.get_everything(q=topic, language='en', sort_by='publishedAt', page_size=limit)
            else:
                articles = newsapi.get_top_headlines(language='en', page_size=limit)

            if not articles.get('articles'):
                return f"📰 No news found{' for ' + topic if topic else ''}"

            result = f"📰 **{'Top Headlines' if not topic else 'News about: ' + topic}**\n\n"

            for i, article in enumerate(articles['articles'][:limit], 1):
                title = article.get('title', 'No title')
                description = article.get('description', '')
                url = article.get('url', '')
                source = article.get('source', {}).get('name', 'Unknown')

                result += f"**{i}. {title}**\n"
                if description:
                    result += f"{description[:150]}...\n"
                result += f"_Source: {source}_\n{url}\n\n"

            return result
        except Exception as e:
            logger.error(f"News API error: {e}")
            return f"❌ Could not fetch news. Error: {str(e)}"
