from typing import Optional

import requests

from config import DEFAULT_CITY, DEFAULT_COUNTRY_CODE, OPENWEATHER_API_KEY


class WeatherService:
    def __init__(self):
        self.api_key = OPENWEATHER_API_KEY

    def get_weather(self, city: Optional[str] = None, country_code: Optional[str] = None, style: str = 'standard') -> str:
        if not self.api_key:
            raise RuntimeError('Weather service not configured')

        city = city or DEFAULT_CITY
        country_code = country_code or DEFAULT_COUNTRY_CODE

        if city and ',' in city:
            city = city.split(',')[-1].strip()

        location = f"{city},{country_code}" if country_code else city
        url = "http://api.openweathermap.org/data/2.5/weather"
        params = {'q': location, 'appid': self.api_key, 'units': 'metric'}

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
