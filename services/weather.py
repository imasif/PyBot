import json
import logging
import re
from typing import Callable, Optional

import requests

import config


logger = logging.getLogger(__name__)

SERVICE_SKILL_COMMANDS = [
    'country_name_to_code',
    'detect_location_learning_request',
    'detect_weather_request',
    'detect_weather_style_learning_request',
    'get_daily_briefing_section',
    'get_briefing_summary',
    'get_weather',
    'get_weather_response',
    'handle_interaction',
    'handle_weather_interaction',
    'normalize_location_for_weather',
]


class WeatherService:
    def __init__(self):
        pass

    @staticmethod
    def _is_invalid_location_phrase(location: Optional[str]) -> bool:
        if not location:
            return True

        normalized = re.sub(r'\s+', ' ', location.strip().lower())
        if not normalized:
            return True

        invalid_exact = {
            'weather',
            'the weather',
            'forecast',
            'the forecast',
            'temperature',
            'today',
            'tomorrow',
            'tonight',
            'now',
            'right now',
            'currently',
        }
        if normalized in invalid_exact:
            return True

        invalid_tokens = {'weather', 'forecast', 'temperature'}
        tokens = set(re.findall(r'[a-zA-Z]+', normalized))
        if tokens and tokens.issubset(invalid_tokens):
            return True

        return False

    def get_weather(self, city: Optional[str] = None, country_code: Optional[str] = None, style: str = 'standard') -> str:
        api_key = getattr(config, 'OPENWEATHER_API_KEY', '')
        if not api_key:
            raise RuntimeError('Weather service not configured')

        city = city or getattr(config, 'DEFAULT_CITY', 'London')
        country_code = country_code or getattr(config, 'DEFAULT_COUNTRY_CODE', 'GB')

        if city and ',' in city:
            city = city.split(',')[0].strip()

        location = f"{city},{country_code}" if country_code else city
        url = "http://api.openweathermap.org/data/2.5/weather"
        params = {'q': location, 'appid': api_key, 'units': 'metric'}

        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        city_name = data['name']
        country = data.get('sys', {}).get('country')
        temp = data['main']['temp']
        feels_like = data['main']['feels_like']
        temp_min = data['main']['temp_min']
        temp_max = data['main']['temp_max']
        humidity = data['main']['humidity']
        description = data['weather'][0]['description'].capitalize()
        wind_speed = data['wind']['speed']
        weather_main = data['weather'][0]['main'].lower()

        emoji_map = {
            'clear': '☀️',
            'clouds': '☁️',
            'rain': '🌧️',
            'drizzle': '🌦️',
            'thunderstorm': '⛈️',
            'snow': '❄️',
            'mist': '🌫️',
            'smoke': '🌫️',
            'haze': '🌫️',
            'fog': '🌫️'
        }

        emoji = emoji_map.get(weather_main, '🌤️')

        text = self._format_text(style, city_name, country, emoji, description,
                                 temp, feels_like, temp_min, temp_max, humidity, wind_speed)
        return text

    def get_weather_response(self, city: Optional[str] = None, country_code: Optional[str] = None, style: str = 'standard') -> str:
        try:
            return self.get_weather(city=city, country_code=country_code, style=style)
        except RuntimeError:
            return "❌ Weather service not configured. Please add OPENWEATHER_API_KEY to .env file.\nGet your free API key at: https://openweathermap.org/api"
        except requests.exceptions.HTTPError as exc:
            logger.error(f"Weather HTTP error: {exc}")
            status_code = getattr(getattr(exc, 'response', None), 'status_code', None)
            city_label = city or getattr(config, 'DEFAULT_CITY', 'London')
            if status_code == 401:
                return "❌ OpenWeather API key is invalid or not yet active. Please verify OPENWEATHER_API_KEY."
            if status_code == 404:
                return f"❌ Could not find weather location '{city_label}'. Try 'weather in City, Country'."
            return f"❌ Could not fetch weather for {city_label}. Please try again."
        except requests.exceptions.RequestException as exc:
            logger.error(f"Weather API error: {exc}")
            city_label = city or getattr(config, 'DEFAULT_CITY', 'London')
            return f"❌ Could not fetch weather for {city_label}. Please check the city name and try again."
        except KeyError as exc:
            logger.error(f"Weather data parsing error: {exc}")
            return "❌ Error parsing weather data."
        except Exception as exc:
            logger.error(f"Unexpected weather error: {exc}")
            return "❌ An unexpected error occurred while fetching weather."

    def get_briefing_summary(self, city: Optional[str] = None, country_code: Optional[str] = None) -> str:
        weather_result = self.get_weather_response(city=city, country_code=country_code, style='standard')
        if "❌" in weather_result:
            return "Weather unavailable"

        temp_match = re.search(r'Temperature:\*\* (.+?)°C', weather_result)
        cond_match = re.search(r'Conditions:\*\* (.+?)\n', weather_result)
        if temp_match and cond_match:
            return f"{temp_match.group(1)}°C, {cond_match.group(1)}"

        first_line = weather_result.split('\n')[0].strip()
        return first_line or "Weather unavailable"

    def get_daily_briefing_section(self, city: Optional[str] = None, country_code: Optional[str] = None) -> str:
        summary = self.get_briefing_summary(city=city, country_code=country_code)
        return f"🌤️ **Weather:**\n{summary}\n\n"

    def detect_weather_request(
        self,
        text,
        user_id=None,
        get_user_context: Optional[Callable] = None,
        save_user_context: Optional[Callable] = None,
        check_learned_patterns: Optional[Callable] = None,
        learn_from_interaction: Optional[Callable] = None,
        ask_ollama: Optional[Callable] = None,
    ):
        text_lower = text.lower().strip()

        if text_lower in ['detailed', 'detailed?', 'brief', 'brief?', 'default', 'default?']:
            if user_id and get_user_context:
                last_city = get_user_context(user_id, 'last_weather_city')
                last_country = get_user_context(user_id, 'last_weather_country')
                if last_city:
                    return {'is_weather': True, 'city': last_city, 'country_code': last_country}

        weather_patterns = [
            r'(?:what(?:\'s| is)|how(?:\'s| is))? (?:the )?weather',
            r'weather (?:in|for|at)',
            r'(?:check|show|get|tell me)(?: the)? weather',
            r'temperature (?:in|at|for)',
            r'(?:is it|will it) (?:rain|snow|sunny|cold|hot)',
            r'forecast (?:for|in)?',
        ]

        for pattern in weather_patterns:
            if re.search(pattern, text_lower):
                city_match = re.search(r'(?:in|for|at) ([a-zA-Z\s,]+)(?:\?|$)', text_lower)
                if city_match:
                    location = city_match.group(1).strip()

                    style_only_patterns = [
                        r'^(?:brief|short|detailed|detail|default|standard)\s+mode$',
                        r'^(?:brief|short|detailed|detail|default|standard)$',
                        r'^(?:news\s*like|news-like)\s+(?:brief|mode)$'
                    ]
                    if any(re.search(style_pattern, location, re.IGNORECASE) for style_pattern in style_only_patterns):
                        city_match = None
                    else:
                        location = re.sub(r'\b(?:brief|short|detailed|detail|default|standard)\s+mode\b', '', location, flags=re.IGNORECASE).strip(' ,')
                        location = re.sub(r'\b(?:in\s+)?(?:brief|short|detailed|detail|default|standard)\b$', '', location, flags=re.IGNORECASE).strip(' ,')

                    if not city_match:
                        location = None

                    if location:
                        location = re.sub(r'\b(today|tonight|tomorrow|now|currently|right now)\b', '', location, flags=re.IGNORECASE).strip(' ,')
                        if self._is_invalid_location_phrase(location):
                            location = None

                    if location:

                        normalized = self.normalize_location_for_weather(location, ask_ollama=ask_ollama)
                        city = (normalized or {}).get('city') if normalized else None
                        country_code = (normalized or {}).get('country_code') if normalized else None
                        if not city:
                            city = location

                        result = {'is_weather': True, 'city': city, 'country_code': country_code}

                        return result

                if user_id and check_learned_patterns:
                    learned_intent = check_learned_patterns(user_id, text_lower, 'weather')
                    if learned_intent:
                        parsed = self._parse_weather_intent(learned_intent)
                        if parsed:
                            city = parsed.get('city')
                            country_code = parsed.get('country_code')
                            if user_id and get_user_context and not country_code:
                                country_code = get_user_context(user_id, 'last_weather_country')
                            return {'is_weather': True, 'city': city, 'country_code': country_code}
                        if learned_intent.startswith('weather_style:'):
                            pass

                if user_id and get_user_context:
                    last_city = get_user_context(user_id, 'last_weather_city')
                    last_country = get_user_context(user_id, 'last_weather_country')

                    if last_city:
                        if ',' in last_city:
                            normalized = self.normalize_location_for_weather(last_city, ask_ollama=ask_ollama)
                            if normalized and normalized.get('city'):
                                last_city = normalized.get('city')
                                if not last_country:
                                    last_country = normalized.get('country_code')
                                if save_user_context:
                                    save_user_context(user_id, 'last_weather_city', last_city)
                                    if last_country:
                                        save_user_context(user_id, 'last_weather_country', last_country)
                        return {'is_weather': True, 'city': last_city, 'country_code': last_country}

                return {'is_weather': True, 'city': 'ASK_USER', 'country_code': None}

        return None

    def handle_weather_interaction(
        self,
        text,
        user_id,
        nlu_intent=None,
        get_user_context: Optional[Callable] = None,
        save_user_context: Optional[Callable] = None,
        check_learned_patterns: Optional[Callable] = None,
        learn_from_interaction: Optional[Callable] = None,
        ask_ollama: Optional[Callable] = None,
    ):
        text_lower = (text or '').lower().strip()

        learned_location = self.detect_location_learning_request(text, ask_ollama=ask_ollama)
        if learned_location:
            city = learned_location.get('city')
            country_code = learned_location.get('country_code')
            raw_location = learned_location.get('raw_location')

            if save_user_context and city:
                save_user_context(user_id, 'last_weather_city', city)
            if save_user_context and country_code:
                save_user_context(user_id, 'last_weather_country', country_code)

            if learn_from_interaction and city:
                learned_intent = self._encode_weather_intent(city, country_code)
                learn_from_interaction(user_id, text_lower, 'weather', learned_intent)

            reply = f"📍 Got it! I saved your default location as: *{raw_location}*\n"
            reply += f"🌆 Weather city: *{city}*\n"
            if country_code:
                reply += f"🌍 Country code: `{country_code}`\n"
            reply += "\n"
            reply += "Now when you ask just *weather*, I'll use this location."

            return {'handled': True, 'reply': reply, 'parse_mode': 'MARKDOWN'}

        weather_style = self.detect_weather_style_learning_request(text)
        if weather_style:
            selected_style = weather_style.get('style')
            explicit_learning = weather_style.get('explicit_learning', False)

            if save_user_context:
                save_user_context(user_id, 'weather_response_style', selected_style)
            if learn_from_interaction:
                learn_from_interaction(user_id, text_lower, 'weather', f'weather_style:{selected_style}')

            if explicit_learning and not self.detect_weather_request(
                text,
                user_id=user_id,
                get_user_context=get_user_context,
                save_user_context=save_user_context,
                check_learned_patterns=check_learned_patterns,
                learn_from_interaction=learn_from_interaction,
                ask_ollama=ask_ollama,
            ):
                style_text = "news-like brief" if selected_style == 'brief' else "detailed/default"
                reply = f"✅ Learned! I'll use *{style_text}* format for your weather replies from now on."
                return {'handled': True, 'reply': reply, 'parse_mode': 'MARKDOWN'}

        weather_detection = None
        if nlu_intent == 'weather':
            weather_detection = self.detect_weather_request(
                'weather',
                user_id=user_id,
                get_user_context=get_user_context,
                save_user_context=save_user_context,
                check_learned_patterns=check_learned_patterns,
                learn_from_interaction=learn_from_interaction,
                ask_ollama=ask_ollama,
            )
        if not weather_detection:
            weather_detection = self.detect_weather_request(
                text,
                user_id=user_id,
                get_user_context=get_user_context,
                save_user_context=save_user_context,
                check_learned_patterns=check_learned_patterns,
                learn_from_interaction=learn_from_interaction,
                ask_ollama=ask_ollama,
            )

        if not (weather_detection and weather_detection.get('is_weather')):
            return None

        city = weather_detection.get('city')
        country_code = weather_detection.get('country_code')
        preferred_style = (
            (weather_style.get('style') if weather_style else None)
            or (get_user_context(user_id, 'weather_response_style') if get_user_context else None)
            or 'standard'
        )

        previous_city = get_user_context(user_id, 'last_weather_city') if get_user_context else None
        previous_country = get_user_context(user_id, 'last_weather_country') if get_user_context else None

        if city == 'ASK_USER':
            ask_message = """🌍 *Please specify the city and country for weather information*

📝 *Format:* `weather in [city], [country]`

*Examples:*
• weather in London, UK
• weather in Tokyo, Japan
• weather in New York, USA
• weather in Paris, France

_Or just reply with the city name if it's unique_"""
            return {'handled': True, 'reply': ask_message, 'parse_mode': 'MARKDOWN'}

        weather_result = self.get_weather_response(city, country_code, preferred_style)

        if city and city != 'ASK_USER' and '❌' not in weather_result:
            if save_user_context:
                save_user_context(user_id, 'last_weather_city', city)
                if country_code:
                    save_user_context(user_id, 'last_weather_country', country_code)

            if learn_from_interaction:
                intent = self._encode_weather_intent(city, country_code)
                learn_from_interaction(user_id, text_lower, 'weather', intent)

            normalized_new_city = city.strip().lower()
            normalized_prev_city = (previous_city or '').strip().lower()
            normalized_new_country = (country_code or '').strip().upper()
            normalized_prev_country = (previous_country or '').strip().upper()
            location_changed = (
                normalized_new_city != normalized_prev_city
                or (normalized_new_country and normalized_new_country != normalized_prev_country)
            )

            if location_changed:
                weather_result += "\n\n_📍 Default location updated._"

        return {'handled': True, 'reply': weather_result, 'parse_mode': 'MARKDOWN'}

    def handle_interaction(
        self,
        text,
        user_id,
        nlu_intent=None,
        get_user_context: Optional[Callable] = None,
        save_user_context: Optional[Callable] = None,
        check_learned_patterns: Optional[Callable] = None,
        learn_from_interaction: Optional[Callable] = None,
        ask_ollama: Optional[Callable] = None,
    ):
        return self.handle_weather_interaction(
            text,
            user_id,
            nlu_intent=nlu_intent,
            get_user_context=get_user_context,
            save_user_context=save_user_context,
            check_learned_patterns=check_learned_patterns,
            learn_from_interaction=learn_from_interaction,
            ask_ollama=ask_ollama,
        )

    @staticmethod
    def _encode_weather_intent(city, country_code=None):
        safe_city = (city or '').strip()
        safe_country = (country_code or '').strip().upper()
        if safe_country:
            return f"weather:{safe_city}|{safe_country}"
        return f"weather:{safe_city}"

    @staticmethod
    def _parse_weather_intent(learned_intent):
        if not learned_intent.startswith('weather:'):
            return None

        payload = learned_intent.split(':', 1)[1].strip()
        if not payload:
            return None

        if '|' in payload:
            city, country_code = payload.split('|', 1)
            city = city.strip()
            country_code = country_code.strip().upper() or None
            if city:
                return {'city': city, 'country_code': country_code}
            return None

        return {'city': payload, 'country_code': None}

    def detect_weather_style_learning_request(self, text):
        text_lower = text.lower().strip()

        wants_weather = ('weather' in text_lower) or ('forecast' in text_lower)
        short_style_followup = text_lower in ['detailed', 'detailed?', 'brief', 'brief?', 'default', 'default?']
        if short_style_followup:
            wants_weather = True
        wants_brief = any(keyword in text_lower for keyword in [
            'brief', 'news like', 'news-like', 'nl brief', 'natural brief', 'short weather', 'weather brief'
        ])
        wants_detail = any(keyword in text_lower for keyword in [
            'detailed weather', 'detail weather', 'full weather', 'normal weather', 'default weather'
        ])

        explicit_learning = any(keyword in text_lower for keyword in [
            'learn', 'remember', 'save', 'set as default', 'use this style', 'from now on'
        ])

        if wants_weather and wants_brief:
            return {'style': 'brief', 'explicit_learning': explicit_learning}
        if wants_weather and wants_detail:
            return {'style': 'standard', 'explicit_learning': explicit_learning}

        return None

    @staticmethod
    def country_name_to_code(country_name):
        if not country_name:
            return None

        name = country_name.strip().lower()
        mapping = {
            "bangladesh": "BD",
            "bd": "BD",
            "united kingdom": "GB",
            "uk": "GB",
            "great britain": "GB",
            "united states": "US",
            "usa": "US",
            "us": "US",
            "japan": "JP",
            "france": "FR",
            "india": "IN",
            "canada": "CA",
        }
        return mapping.get(name, country_name.upper() if len(country_name.strip()) <= 3 else None)

    def normalize_location_for_weather(self, raw_location, ask_ollama: Optional[Callable] = None):
        if not raw_location:
            return None

        if ask_ollama:
            try:
                prompt = f'''Extract city and country from this location for weather API use.

Location: "{raw_location}"

Return ONLY valid JSON:
{{"city": "...", "country_name": "...", "country_code": "..."}}

Rules:
- city must be the main weather city (not neighborhood)
- country_code should be ISO 2-letter uppercase when possible
- if unsure, keep best guess
'''
                ai_response = ask_ollama(prompt, [])
                json_match = re.search(r'\{[\s\S]*\}', ai_response)
                if json_match:
                    parsed = json.loads(json_match.group())
                    city = (parsed.get('city') or '').strip()
                    country_name = (parsed.get('country_name') or '').strip()
                    country_code = (parsed.get('country_code') or '').strip().upper()
                    if not country_code and country_name:
                        country_code = self.country_name_to_code(country_name)
                    if city:
                        return {
                            "city": city,
                            "country_name": country_name or None,
                            "country_code": country_code or None,
                            "raw_location": raw_location,
                        }
            except Exception:
                pass

        parts = [part.strip() for part in raw_location.split(',') if part.strip()]
        if len(parts) >= 2:
            country_part = parts[-1]
            city_part = parts[-2] if len(parts) >= 3 else parts[0]
            return {
                "city": city_part,
                "country_name": country_part,
                "country_code": self.country_name_to_code(country_part),
                "raw_location": raw_location,
            }

        return {
            "city": raw_location.strip(),
            "country_name": None,
            "country_code": None,
            "raw_location": raw_location,
        }

    def detect_location_learning_request(self, text, ask_ollama: Optional[Callable] = None):
        text_normalized = text.strip()

        patterns = [
            r'^(?:learn|remember|save) my location\s*[:\-]?\s*(.+)$',
            r'^(?:my location is|set my location to)\s+(.+)$',
            r'^(?:use|set) (.+) as my default location$'
        ]

        for pattern in patterns:
            match = re.search(pattern, text_normalized, re.IGNORECASE)
            if match:
                raw_location = match.group(1).strip().strip('.')
                if not raw_location:
                    return None

                return self.normalize_location_for_weather(raw_location, ask_ollama=ask_ollama)

        return None

    def _format_text(self, style, city_name, country, emoji, description,
                     temp, feels_like, temp_min, temp_max, humidity, wind_speed):
        if style == 'brief':
            return (
                f"📰 *Weather Brief — {city_name}, {country}*\n\n"
                f"{emoji} {description}. Temperature is around *{temp:.1f}°C* (feels like {feels_like:.1f}°C).\n"
                f"Humidity is {humidity}% with wind at {wind_speed} m/s.\n"
                f"Today's range: {temp_min:.1f}°C to {temp_max:.1f}°C.\n\n"
                "_Need the detailed forecast? Ask for detailed weather._"
            )

        return (
            f"{emoji} *Weather in {city_name}, {country}*\n\n"
            f"🌡️ *Temperature:* {temp}°C (feels like {feels_like}°C)\n"
            f"📊 *Range:* {temp_min}°C - {temp_max}°C\n"
            f"💧 *Humidity:* {humidity}%\n"
            f"🌤️ *Conditions:* {description}\n"
            f"💨 *Wind:* {wind_speed} m/s\n"
        )
