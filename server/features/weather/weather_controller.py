from fastapi import APIRouter
from server.features.weather.models import WeatherResponse
from server.features.weather.weather_service import weather_service

weather_router = APIRouter(prefix="/weather", tags=["weather"])

@weather_router.get("/current", response_model=WeatherResponse)
async def get_current_weather() -> WeatherResponse:
    return await weather_service.get_current_weather()
