from ..schemas import IntakeOutput, WeatherOutput
from ..weather_data import build_weather_output


async def run_weather(intake: IntakeOutput) -> WeatherOutput:
    return await build_weather_output(intake)
