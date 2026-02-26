# Weather Skill

**Purpose:** Provide current weather data for a requested location using OpenWeatherMap.

**Behavior:**
- `get_weather` expects a city and country code, falls back to the defaults from `config`, and returns a formatted response with temperature, humidity, and wind.
- The service gracefully handles missing credentials by returning a clear setup message.

**Triggers:** Phrases like "weather", "forecast", "is it going to rain", or "temperature" combined with a place name.
