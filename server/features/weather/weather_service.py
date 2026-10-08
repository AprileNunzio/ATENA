import datetime
import httpx
from server.features.weather.models import WeatherCondition, WeatherResponse

class WeatherService:
    def __init__(self, default_lat: float = 41.9028, default_lon: float = 12.4964, city_name: str = "Roma") -> None:
        self._lat = default_lat
        self._lon = default_lon
        self._city = city_name
        self._cached_weather: WeatherResponse | None = None
        self._cache_timestamp: float = 0.0
        self._cache_ttl_sec: float = 900.0

    async def get_current_weather(self) -> WeatherResponse:
        now = datetime.datetime.now()
        now_ts = now.timestamp()
        if self._cached_weather and (now_ts - self._cache_timestamp < self._cache_ttl_sec):
            return self._cached_weather

        weather = await self._fetch_from_provider(now)
        self._cached_weather = weather
        self._cache_timestamp = now_ts
        return weather

    async def _fetch_from_provider(self, now: datetime.datetime) -> WeatherResponse:
        is_day = 6 <= now.hour < 20
        url = f"https://api.open-meteo.com/v1/forecast?latitude={self._lat}&longitude={self._lon}&current_weather=true"
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                res = await client.get(url)
                if res.status_code == 200:
                    data = res.json().get("current_weather", {})
                    code = data.get("weathercode", 0)
                    condition = self._map_wmo_code(code, is_day)
                    return WeatherResponse(
                        condition=condition,
                        temperature_celsius=float(data.get("temperature", 20.0)),
                        humidity_percent=60,
                        description=condition.value.replace("_", " ").title(),
                        wind_kmh=float(data.get("windspeed", 8.0)),
                        city=self._city,
                        is_day=is_day,
                    )
        except Exception:
            pass

        return self._generate_fallback(now, is_day)

    def _map_wmo_code(self, code: int, is_day: bool) -> WeatherCondition:
        if code == 0:
            return WeatherCondition.CLEAR_DAY if is_day else WeatherCondition.CLEAR_NIGHT
        if code in (1, 2, 3):
            return WeatherCondition.CLOUDY
        if code in (45, 48):
            return WeatherCondition.FOG
        if code in (51, 53, 55, 61, 63, 65, 80, 81, 82):
            return WeatherCondition.RAIN
        if code in (71, 73, 75, 77, 85, 86):
            return WeatherCondition.SNOW
        if code in (95, 96, 99):
            return WeatherCondition.STORM
        return WeatherCondition.CLEAR_DAY if is_day else WeatherCondition.CLEAR_NIGHT

    def _generate_fallback(self, now: datetime.datetime, is_day: bool) -> WeatherResponse:
        default_condition = WeatherCondition.CLEAR_DAY if is_day else WeatherCondition.CLEAR_NIGHT
        return WeatherResponse(
            condition=default_condition,
            temperature_celsius=21.5 if is_day else 16.0,
            humidity_percent=55,
            description="Sereno" if is_day else "Notte Serena",
            wind_kmh=7.5,
            city=self._city,
            is_day=is_day,
        )

weather_service = WeatherService()
