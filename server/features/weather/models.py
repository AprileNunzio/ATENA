from enum import Enum
from pydantic import BaseModel, Field

class WeatherCondition(str, Enum):
    CLEAR_DAY = "clear_day"
    CLEAR_NIGHT = "clear_night"
    CLOUDY = "cloudy"
    RAIN = "rain"
    STORM = "storm"
    SNOW = "snow"
    FOG = "fog"

class WeatherResponse(BaseModel):
    condition: WeatherCondition
    temperature_celsius: float = Field(..., ge=-60.0, le=70.0)
    humidity_percent: int = Field(..., ge=0, le=100)
    description: str
    wind_kmh: float = Field(..., ge=0.0)
    city: str
    is_day: bool
