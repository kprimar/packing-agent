"""
Fetches weather data for a destination and date range using the Open-Meteo API.
No API key required.
"""

import requests
from datetime import datetime, date, timedelta


def geocode(city: str) -> tuple[float, float, str]:
    """Return (latitude, longitude, resolved_name) for a city name."""
    resp = requests.get(
        "https://geocoding-api.open-meteo.com/v1/search",
        params={"name": city, "count": 1, "language": "en", "format": "json"},
        timeout=10,
    )
    resp.raise_for_status()
    results = resp.json().get("results")
    if not results:
        raise ValueError(f"Could not find location: '{city}'. Try a more specific city name.")
    r = results[0]
    name_parts = [r["name"]]
    if r.get("admin1"):
        name_parts.append(r["admin1"])
    if r.get("country"):
        name_parts.append(r["country"])
    return r["latitude"], r["longitude"], ", ".join(name_parts)


def _fetch_daily(url: str, lat: float, lon: float, start: str, end: str) -> dict:
    resp = requests.get(
        url,
        params={
            "latitude": lat,
            "longitude": lon,
            "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,weathercode",
            "temperature_unit": "celsius",
            "timezone": "auto",
            "start_date": start,
            "end_date": end,
        },
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json().get("daily", {})


def get_weather(city: str, start_date: str, end_date: str) -> dict:
    """
    Return weather summary for a city and date range.

    For dates within the next 16 days: uses live forecast data.
    For dates further out or in the past: uses the same calendar period from last year
    as a historical approximation.
    """
    lat, lon, resolved_name = geocode(city)

    today = date.today()
    start = datetime.strptime(start_date, "%Y-%m-%d").date()
    end = datetime.strptime(end_date, "%Y-%m-%d").date()

    forecast_horizon = today + timedelta(days=16)
    use_historical = end > forecast_horizon or end <= today

    if use_historical:
        # Same window last year as a climate approximation
        hist_start = start.replace(year=start.year - 1)
        hist_end = end.replace(year=end.year - 1)
        daily = _fetch_daily(
            "https://archive-api.open-meteo.com/v1/archive",
            lat, lon,
            hist_start.isoformat(),
            hist_end.isoformat(),
        )
    else:
        daily = _fetch_daily(
            "https://api.open-meteo.com/v1/forecast",
            lat, lon,
            start_date,
            end_date,
        )

    highs = [t for t in daily.get("temperature_2m_max", []) if t is not None]
    lows = [t for t in daily.get("temperature_2m_min", []) if t is not None]
    precip = [p for p in daily.get("precipitation_sum", []) if p is not None]
    codes = [c for c in daily.get("weathercode", []) if c is not None]

    avg_high = round(sum(highs) / len(highs), 1) if highs else None
    avg_low = round(sum(lows) / len(lows), 1) if lows else None
    avg_temp = round((avg_high + avg_low) / 2, 1) if avg_high is not None and avg_low is not None else None
    total_precip = round(sum(precip), 1) if precip else 0.0
    conditions = _summarize_conditions(codes)

    return {
        "location": resolved_name,
        "start_date": start_date,
        "end_date": end_date,
        "avg_high_c": avg_high,
        "avg_low_c": avg_low,
        "avg_temp_c": avg_temp,
        "total_precip_mm": total_precip,
        "conditions": conditions,
        "is_historical": use_historical,
    }


def _summarize_conditions(codes: list) -> str:
    if not codes:
        return "mixed conditions"

    # WMO weather code categories
    has_thunder = any(c >= 95 for c in codes)
    has_heavy_snow = any(75 <= c <= 77 or 85 <= c <= 86 for c in codes)
    has_snow = any(70 <= c <= 86 for c in codes)
    has_rain = any(51 <= c <= 67 for c in codes)
    has_drizzle = any(51 <= c <= 57 for c in codes)
    has_fog = any(c in (45, 48) for c in codes)
    clear_days = sum(1 for c in codes if c <= 1)
    cloudy_days = sum(1 for c in codes if c >= 2)

    parts = []
    if has_thunder:
        parts.append("thunderstorms")
    if has_heavy_snow:
        parts.append("heavy snow")
    elif has_snow:
        parts.append("snow")
    if has_rain and not has_thunder:
        parts.append("rain")
    elif has_drizzle and not has_thunder:
        parts.append("drizzle")
    if has_fog:
        parts.append("fog")
    if not parts:
        if clear_days >= len(codes) * 0.6:
            parts.append("mostly sunny")
        elif cloudy_days >= len(codes) * 0.6:
            parts.append("mostly cloudy")
        else:
            parts.append("partly cloudy")

    return ", ".join(parts)


def format_weather_context(weather: dict) -> str:
    """Return a weather summary string suitable for injecting into the Claude system prompt."""
    c_to_f = lambda c: round(c * 9 / 5 + 32, 1) if c is not None else None

    high_f = c_to_f(weather["avg_high_c"])
    low_f = c_to_f(weather["avg_low_c"])
    avg_f = c_to_f(weather["avg_temp_c"])

    lines = [
        f"Destination: {weather['location']}",
        f"Travel dates: {weather['start_date']} to {weather['end_date']}",
    ]

    if weather["avg_high_c"] is not None:
        lines.append(f"Average high: {weather['avg_high_c']}°C ({high_f}°F)")
        lines.append(f"Average low: {weather['avg_low_c']}°C ({low_f}°F)")
        lines.append(f"Average temperature: {weather['avg_temp_c']}°C ({avg_f}°F)")

    lines.append(f"Expected conditions: {weather['conditions']}")
    lines.append(f"Total expected precipitation: {weather['total_precip_mm']}mm")

    if weather["is_historical"]:
        lines.append("Note: Travel dates are beyond the 16-day forecast window; weather is based on historical data from the same period last year.")

    return "\n".join(lines)
