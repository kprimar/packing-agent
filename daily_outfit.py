"""
Daily outfit email script.
Fetches tomorrow's weather, asks Claude for an outfit recommendation,
and emails it to the configured recipient.

Schedule at 8PM daily with:  powershell -ExecutionPolicy Bypass setup_scheduler.ps1
Run manually to test:        python daily_outfit.py
"""

import os
import sys
from datetime import date, timedelta

from dotenv import load_dotenv

load_dotenv()

from agent.config import get_default_location, get_work_days, get_dress_code
from agent.weather import get_weather, format_weather_context
from agent import packer
from agent.emailer import send_email

RECIPIENT = "kprimar@gmail.com"


def main():
    location = get_default_location()
    if not location:
        print("No default location set — open the app and set one in Settings (⚙).")
        sys.exit(1)

    tomorrow = date.today() + timedelta(days=1)
    day_name = tomorrow.strftime("%A")
    date_str = f"{tomorrow.strftime('%B')} {tomorrow.day}"

    work_days = get_work_days()
    dress_code = get_dress_code()
    is_work_day = day_name in work_days

    if is_work_day:
        user_context = f"Tomorrow is {day_name} — a work/school day."
        if dress_code:
            user_context += f" Dress code: {dress_code}."
    else:
        user_context = f"Tomorrow is {day_name} — a day off, no work or school."

    print(f"Fetching weather for {location} on {date_str}…")
    try:
        w = get_weather(location, tomorrow.isoformat(), tomorrow.isoformat())
    except Exception as exc:
        print(f"Could not fetch weather: {exc}")
        sys.exit(1)

    ctx = format_weather_context(w)
    if w.get("is_historical"):
        user_context += " (Weather is based on historical data — live forecast unavailable this far out.)"

    print("Asking Claude for a recommendation…")
    try:
        reply, _ = packer.get_outfit_email_recommendation(ctx, user_context)
    except Exception as exc:
        print(f"Could not reach Claude: {exc}")
        sys.exit(1)

    subject = f"Outfit for tomorrow — {day_name}, {date_str}"
    body = f"{reply}\n\n— Your Packing Agent"

    print(f"Sending email to {RECIPIENT}…")
    try:
        send_email(subject, body, RECIPIENT)
        print("Done.")
    except Exception as exc:
        print(f"Failed to send email: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
