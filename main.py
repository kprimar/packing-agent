"""
Packing Agent — CLI entry point.

Usage: python main.py
"""

import sys
from datetime import datetime

from colorama import Fore, Style, init

from agent.weather import get_weather, format_weather_context
from agent import packer

init(autoreset=True)

EXIT_PHRASES = {"quit", "exit", "done", "bye", "goodbye", "that's all", "thats all", "no more questions"}


def _prompt(label: str) -> str:
    return input(f"{Fore.CYAN}{label}{Style.RESET_ALL}").strip()


def _parse_date(raw: str) -> str:
    """Try a few common date formats and return YYYY-MM-DD, or raise ValueError."""
    formats = ["%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%B %d %Y", "%b %d %Y", "%B %d, %Y", "%b %d, %Y"]
    for fmt in formats:
        try:
            return datetime.strptime(raw.strip(), fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    raise ValueError(f"Could not parse date: '{raw}'. Please use YYYY-MM-DD format.")


def _get_dates() -> tuple[str, str]:
    while True:
        raw_start = _prompt("Departure date (e.g. 2026-08-10): ")
        try:
            start = _parse_date(raw_start)
        except ValueError as e:
            print(f"{Fore.YELLOW}{e}{Style.RESET_ALL}")
            continue

        raw_end = _prompt("Return date   (e.g. 2026-08-17): ")
        try:
            end = _parse_date(raw_end)
        except ValueError as e:
            print(f"{Fore.YELLOW}{e}{Style.RESET_ALL}")
            continue

        if end < start:
            print(f"{Fore.YELLOW}Return date must be after departure date.{Style.RESET_ALL}")
            continue

        return start, end


def _is_exit(text: str) -> bool:
    return text.lower().strip().rstrip("!.") in EXIT_PHRASES


def main() -> None:
    print(f"\n{Fore.CYAN}=== Packing Agent ==={Style.RESET_ALL}")
    print("I'll help you pack the right clothes for your trip.\n")

    # --- Collect trip info ---
    destination = _prompt("Where are you traveling to? ")
    if not destination:
        print(f"{Fore.RED}Destination cannot be empty.{Style.RESET_ALL}")
        sys.exit(1)

    start_date, end_date = _get_dates()

    # --- Fetch weather ---
    print(f"\n{Fore.YELLOW}Fetching weather for {destination}...{Style.RESET_ALL}")
    try:
        weather = get_weather(destination, start_date, end_date)
    except ValueError as e:
        print(f"{Fore.RED}Location error: {e}{Style.RESET_ALL}")
        sys.exit(1)
    except Exception as e:
        print(f"{Fore.RED}Could not fetch weather data: {e}{Style.RESET_ALL}")
        sys.exit(1)

    weather_context = format_weather_context(weather)
    print(f"\n{Fore.WHITE}{weather_context}{Style.RESET_ALL}\n")

    if weather.get("is_historical"):
        print(f"{Fore.YELLOW}(Using last year's data as a forecast estimate — the live forecast only covers 16 days ahead.){Style.RESET_ALL}\n")

    # --- Start Claude conversation ---
    print(f"{Fore.YELLOW}Generating packing recommendation...{Style.RESET_ALL}\n")
    try:
        reply, messages = packer.start_conversation(weather_context)
    except Exception as e:
        print(f"{Fore.RED}Could not reach Claude: {e}{Style.RESET_ALL}")
        sys.exit(1)

    print(f"{Fore.GREEN}Assistant:{Style.RESET_ALL} {reply}\n")
    print(f"{Fore.WHITE}{'-' * 60}{Style.RESET_ALL}")
    print(f'{Fore.WHITE}Type your answer, or "done" to finish.{Style.RESET_ALL}\n')

    # --- Conversation loop ---
    while True:
        try:
            user_input = _prompt("You: ")
        except (EOFError, KeyboardInterrupt):
            print(f"\n{Fore.CYAN}Have a great trip!{Style.RESET_ALL}")
            break

        if not user_input:
            continue

        if _is_exit(user_input):
            # Give Claude a chance to produce a clean final summary
            try:
                reply, messages = packer.continue_conversation(messages, "I'm all set, thank you!")
                print(f"\n{Fore.GREEN}Assistant:{Style.RESET_ALL} {reply}\n")
            except Exception:
                pass
            print(f"{Fore.CYAN}Have a great trip!{Style.RESET_ALL}")
            break

        try:
            reply, messages = packer.continue_conversation(messages, user_input)
        except Exception as e:
            print(f"{Fore.RED}Error: {e}{Style.RESET_ALL}")
            continue

        print(f"\n{Fore.GREEN}Assistant:{Style.RESET_ALL} {reply}\n")
        print(f"{Fore.WHITE}{'-' * 60}{Style.RESET_ALL}\n")


if __name__ == "__main__":
    main()
