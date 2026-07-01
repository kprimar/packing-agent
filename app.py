"""
Packing Agent — desktop chat UI.
Run: python app.py
"""

import os
import re
import sys
import threading
from datetime import datetime

import customtkinter as ctk
from dotenv import load_dotenv

load_dotenv()

from agent.weather import get_weather, format_weather_context
from agent import packer
from agent.config import (
    get_default_location, set_default_location, clear_default_location,
    get_work_days, set_work_days, get_dress_code, set_dress_code,
)

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


def _clean(text: str) -> str:
    """Strip basic markdown so plain text reads cleanly in a label."""
    text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)
    text = re.sub(r"\*(.*?)\*", r"\1", text)
    text = re.sub(r"^#{1,3}\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"^- ", "• ", text, flags=re.MULTILINE)
    return text.strip()


_WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


def _parse_date(raw: str):
    import re
    from datetime import date, timedelta

    # "next Friday" / "this Friday"
    m = re.match(r"^(next|this)\s+(\w+)$", raw.strip(), re.IGNORECASE)
    if m:
        modifier, day_name = m.group(1).lower(), m.group(2).lower()
        if day_name in _WEEKDAYS:
            target = _WEEKDAYS.index(day_name)
            today = date.today()
            days_ahead = (target - today.weekday()) % 7 or 7
            if modifier == "next":
                days_ahead += 7
            return today + timedelta(days=days_ahead)

    formats = [
        "%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y",
        "%B %d %Y", "%b %d %Y", "%B %d, %Y", "%b %d, %Y",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(raw.strip(), fmt).date()
        except ValueError:
            continue

    import dateparser
    result = dateparser.parse(raw, settings={"PREFER_DATES_FROM": "future"})
    if result:
        return result.date()

    # Last resort: find a date anywhere inside the text (handles "wear tomorrow?", etc.)
    from dateparser.search import search_dates
    hits = search_dates(raw, settings={"PREFER_DATES_FROM": "future", "RETURN_AS_TIMEZONE_AWARE": False})
    if hits:
        return hits[-1][1].date()

    raise ValueError(raw)


def _parse_date_range(raw: str):
    """Parse a date range like 'February 2-15, 2026' or 'Feb 2 - March 15, 2026'.
    Returns (start_date, end_date) or raises ValueError if not a recognized range."""
    text = raw.strip()

    # "Month Day1-Day2, Year"  e.g. "February 2-15, 2026"
    m = re.match(
        r"^([A-Za-z]+)\s+(\d{1,2})\s*[-–]\s*(\d{1,2}),?\s*(\d{4})$",
        text,
    )
    if m:
        month, d1, d2, year = m.group(1), m.group(2), m.group(3), m.group(4)
        return _parse_date(f"{month} {d1}, {year}"), _parse_date(f"{month} {d2}, {year}")

    # "Month Day1 - Month Day2, Year"  e.g. "February 2 - March 15, 2026"
    m = re.match(
        r"^([A-Za-z]+)\s+(\d{1,2})\s*[-–]\s*([A-Za-z]+)\s+(\d{1,2}),?\s*(\d{4})$",
        text,
    )
    if m:
        m1, d1, m2, d2, year = m.group(1), m.group(2), m.group(3), m.group(4), m.group(5)
        return _parse_date(f"{m1} {d1}, {year}"), _parse_date(f"{m2} {d2}, {year}")

    # "Month Day1 to [Month] Day2, Year"  e.g. "February 2 to 15, 2026" or "Feb 2 to March 15, 2026"
    m = re.match(
        r"^([A-Za-z]+)\s+(\d{1,2})\s+to\s+(?:([A-Za-z]+)\s+)?(\d{1,2}),?\s*(\d{4})$",
        text,
        re.IGNORECASE,
    )
    if m:
        m1, d1, m2, d2, year = m.group(1), m.group(2), m.group(3) or m.group(1), m.group(4), m.group(5)
        return _parse_date(f"{m1} {d1}, {year}"), _parse_date(f"{m2} {d2}, {year}")

    raise ValueError(f"Not a recognizable date range: {raw}")


def _parse_outfit_date_range(raw: str):
    """Return (start_date, end_date) for natural outfit-date inputs like 'today', 'this week'."""
    import re
    from datetime import date, timedelta

    text = raw.strip().lower()
    today = date.today()

    if text in ("today", ""):
        return today, today
    if text == "tomorrow":
        return today + timedelta(1), today + timedelta(1)
    if text in ("this week", "next 7 days", "the week"):
        return today, today + timedelta(6)
    if text in ("next 3 days", "3 days"):
        return today, today + timedelta(2)

    m = re.match(r"next (\d+) days?", text)
    if m:
        n = int(m.group(1))
        return today, today + timedelta(n - 1)

    try:
        return _parse_date_range(raw)
    except ValueError:
        pass

    d = _parse_date(raw)
    return d, d


def _parse_outfit_date_and_location(raw: str):
    """Parse outfit date input that may include an optional 'in <Location>' suffix.
    Returns (start_date, end_date, location_or_None).
    """
    if " in " in raw.lower():
        parts = raw.rsplit(" in ", 1)
        date_part = parts[0].strip()
        loc_part = parts[1].strip()
        if loc_part:
            try:
                start, end = _parse_outfit_date_range(date_part)
                return start, end, loc_part
            except ValueError:
                pass
    start, end = _parse_outfit_date_range(raw)
    return start, end, None


class PackingAgentApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Packing Agent")
        self.geometry("680x740")
        self.minsize(500, 520)

        self._mode = None
        self._state = "AWAITING_MODE"
        self._destination = None
        self._start_date = None
        self._end_date = None
        self._messages = []

        self._build_ui()

        if get_default_location():
            self.after(150, self._launch_daily_outfit)
        else:
            self.after(150, lambda: self._agent_say(
                "Hi! Would you like outfit recommendations for a specific day, "
                "or help packing for a trip?"
            ))

    # ── Layout ────────────────────────────────────────────────────────────────

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=16, pady=(12, 0))
        header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            header, text="Packing Agent",
            font=ctk.CTkFont(size=22, weight="bold"),
        ).grid(row=0, column=0, pady=6)

        ctk.CTkButton(
            header, text="⚙",
            width=36, height=36,
            font=ctk.CTkFont(size=18),
            fg_color="transparent",
            hover_color=("gray80", "gray25"),
            command=self._open_settings,
        ).grid(row=0, column=1, sticky="e")

        self._chat = ctk.CTkScrollableFrame(self, fg_color=("gray88", "gray13"))
        self._chat.grid(row=1, column=0, padx=16, pady=8, sticky="nsew")
        self._chat.grid_columnconfigure(0, weight=1)

        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.grid(row=2, column=0, padx=16, pady=(0, 16), sticky="ew")
        bar.grid_columnconfigure(0, weight=1)

        self._entry = ctk.CTkEntry(
            bar, placeholder_text="Type a message…",
            height=44, font=ctk.CTkFont(size=14),
        )
        self._entry.grid(row=0, column=0, padx=(0, 10), sticky="ew")
        self._entry.bind("<Return>", lambda _e: self._on_send())

        self._btn = ctk.CTkButton(
            bar, text="Send", width=90, height=44,
            font=ctk.CTkFont(size=14), command=self._on_send,
        )
        self._btn.grid(row=0, column=1)
        self._entry.focus()

    # ── Bubbles ───────────────────────────────────────────────────────────────

    def _agent_say(self, text: str):
        self._bubble(text, is_user=False)

    def _user_say(self, text: str):
        self._bubble(text, is_user=True)

    def _bubble(self, text: str, is_user: bool):
        row = self._chat.grid_size()[1]
        try:
            w_logical = int(self.geometry().split("x")[0])
        except Exception:
            w_logical = 680
        wrap = max(w_logical - 220, 300)

        outer = ctk.CTkFrame(self._chat, fg_color="transparent")
        outer.grid(row=row, column=0, sticky="ew", pady=3, padx=6)
        outer.grid_columnconfigure(0 if is_user else 1, weight=1)

        color = ("#2b5ea7", "#2b5ea7") if is_user else ("#d4d4d4", "#2d2d2d")
        tcolor = ("white", "white") if is_user else ("black", "white")

        frame = ctk.CTkFrame(outer, fg_color=color, corner_radius=14)
        frame.grid(row=0, column=1 if is_user else 0, sticky="e" if is_user else "w")

        ctk.CTkLabel(
            frame, text=text,
            wraplength=wrap, justify="left", anchor="w",
            text_color=tcolor,
            font=ctk.CTkFont(size=13),
        ).pack(padx=14, pady=9)

        self.after(80, self._scroll_bottom)

    def _scroll_bottom(self):
        try:
            self._chat._parent_canvas.yview_moveto(1.0)
        except Exception:
            pass

    # ── Busy state ────────────────────────────────────────────────────────────

    def _busy(self, on: bool, label: str = "Thinking…"):
        if on:
            self._btn.configure(text=label, state="disabled")
            self._entry.configure(state="disabled")
        else:
            self._btn.configure(text="Send", state="normal")
            self._entry.configure(state="normal")
            self._entry.focus()

    # ── Daily outfit on launch ────────────────────────────────────────────────

    def _launch_daily_outfit(self):
        from datetime import date, timedelta
        tomorrow = date.today() + timedelta(days=1)
        self._mode = "outfit"
        self._destination = get_default_location()
        self._start_date = tomorrow
        self._end_date = tomorrow
        self._agent_say(f"Good morning! Let me grab tomorrow's outfit for {self._destination}…")
        self._busy(True, "Fetching weather…")
        threading.Thread(target=self._do_daily_outfit, daemon=True).start()

    def _do_daily_outfit(self):
        from datetime import date, timedelta
        tomorrow = date.today() + timedelta(days=1)
        day_name = tomorrow.strftime("%A")
        work_days = get_work_days()
        dress_code = get_dress_code()
        is_work_day = day_name in work_days

        if is_work_day:
            user_context = f"Tomorrow is {day_name} — a work/school day."
            if dress_code:
                user_context += f" Dress code: {dress_code}."
        else:
            user_context = f"Tomorrow is {day_name} — a day off, no work or school."

        try:
            w = get_weather(self._destination, tomorrow.isoformat(), tomorrow.isoformat())
            ctx = format_weather_context(w)
            if w.get("is_historical"):
                user_context += " (Weather is based on historical data — live forecast unavailable this far out.)"
            reply, msgs = packer.get_outfit_email_recommendation(ctx, user_context)
            self._messages = msgs
            self.after(0, lambda r=reply: self._reply(r))
        except Exception as exc:
            self.after(0, lambda e=exc: self._error(f"Could not load daily outfit: {e}"))

    # ── Settings dialog ───────────────────────────────────────────────────────

    def _open_settings(self):
        dialog = ctk.CTkToplevel(self)
        dialog.title("Settings")
        dialog.geometry("430x400")
        dialog.resizable(False, False)
        dialog.grab_set()

        content = ctk.CTkFrame(dialog, fg_color="transparent")
        content.pack(fill="both", expand=True, padx=24, pady=20)

        # ── Default location ──────────────────────────────────────────────────
        ctk.CTkLabel(
            content, text="Default location",
            font=ctk.CTkFont(size=14, weight="bold"), anchor="w",
        ).pack(fill="x", pady=(0, 6))

        loc_row = ctk.CTkFrame(content, fg_color="transparent")
        loc_row.pack(fill="x")
        loc_row.grid_columnconfigure(0, weight=1)

        loc_entry = ctk.CTkEntry(
            loc_row, placeholder_text="e.g. London, New York, Tokyo",
            font=ctk.CTkFont(size=13), height=36,
        )
        current = get_default_location()
        if current:
            loc_entry.insert(0, current)
        loc_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))

        ctk.CTkButton(
            loc_row, text="Clear", width=70, height=36,
            fg_color=("gray60", "gray35"), hover_color=("gray50", "gray25"),
            command=lambda: loc_entry.delete(0, "end"),
        ).grid(row=0, column=1)

        status = ctk.CTkLabel(
            content, text="", font=ctk.CTkFont(size=12),
            text_color=("red", "#ff6b6b"), anchor="w",
        )
        status.pack(fill="x", pady=(4, 0))

        # ── Work / school days ────────────────────────────────────────────────
        ctk.CTkLabel(
            content, text="Work / school days",
            font=ctk.CTkFont(size=14, weight="bold"), anchor="w",
        ).pack(fill="x", pady=(16, 8))

        days_frame = ctk.CTkFrame(content, fg_color="transparent")
        days_frame.pack(fill="x")

        _SHORT = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        _FULL  = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

        saved_days = get_work_days()
        day_vars = {}
        for i, (short, full) in enumerate(zip(_SHORT, _FULL)):
            var = ctk.BooleanVar(value=full in saved_days)
            day_vars[full] = var
            ctk.CTkCheckBox(
                days_frame, text=short, variable=var,
                width=52, checkbox_width=18, checkbox_height=18,
                font=ctk.CTkFont(size=12),
            ).grid(row=0, column=i, padx=2)

        # ── Dress code ────────────────────────────────────────────────────────
        ctk.CTkLabel(
            content, text="Dress code at work / school",
            font=ctk.CTkFont(size=14, weight="bold"), anchor="w",
        ).pack(fill="x", pady=(20, 8))

        dress_codes = ["Casual", "Business Casual", "Business Formal"]
        saved_code = get_dress_code() or dress_codes[0]
        dress_var = ctk.StringVar(value=saved_code)

        ctk.CTkOptionMenu(
            content, values=dress_codes, variable=dress_var,
            width=220, font=ctk.CTkFont(size=13),
        ).pack(anchor="w")

        # ── Buttons ───────────────────────────────────────────────────────────
        btn_row = ctk.CTkFrame(content, fg_color="transparent")
        btn_row.pack(pady=(24, 0))

        def _save():
            loc = loc_entry.get().strip()
            if loc:
                status.configure(text="Checking location…")
                dialog.update()
                try:
                    from agent.weather import geocode
                    geocode(loc)
                    set_default_location(loc)
                except Exception:
                    status.configure(
                        text="Location not found. Try a city name like 'Vancouver' or 'Tokyo'."
                    )
                    return
            else:
                clear_default_location()

            set_work_days([full for full, var in day_vars.items() if var.get()])
            set_dress_code(dress_var.get())
            dialog.destroy()

        ctk.CTkButton(btn_row, text="Save", width=110, command=_save).grid(row=0, column=0, padx=8)
        ctk.CTkButton(
            btn_row, text="Cancel", width=110,
            fg_color=("gray60", "gray35"), hover_color=("gray50", "gray25"),
            command=dialog.destroy,
        ).grid(row=0, column=1, padx=8)

    # ── Input routing ─────────────────────────────────────────────────────────

    def _on_send(self):
        text = self._entry.get().strip()
        if not text or str(self._btn.cget("state")) == "disabled":
            return
        self._entry.delete(0, "end")
        self._user_say(text)
        try:
            self._route(text)
        except Exception as exc:
            import traceback
            self._agent_say(f"Unexpected error: {type(exc).__name__}: {exc}")
            traceback.print_exc()
            self._busy(False)

    def _route(self, text: str):
        if self._state == "AWAITING_MODE":
            low = text.lower()
            if any(w in low for w in ("outfit", "wear", "what to wear")):
                self._mode = "outfit"
                default = get_default_location()
                self._state = "AWAITING_OUTFIT_DATE"
                if default:
                    self._destination = default
                    self._agent_say(
                        f"Okay, for what day? I'll assume we're talking about {default}, "
                        "unless you specify otherwise."
                    )
                else:
                    self._agent_say(
                        "Okay, for what day? You can also include a location "
                        "(e.g. 'tomorrow in Paris'). Or set a default in Settings (⚙)."
                    )
            elif any(w in low for w in ("pack", "trip", "travel", "traveling", "travelling")):
                self._mode = "packing"
                self._state = "AWAITING_DESTINATION"
                self._agent_say("Where are you traveling to?")
            else:
                self._agent_say(
                    "I can help with outfit recommendations for a specific day, "
                    "or with packing for a trip. Which would you like?"
                )

        elif self._state == "AWAITING_OUTFIT_DATE":
            try:
                start, end, loc_override = _parse_outfit_date_and_location(text)
                self._start_date = start
                self._end_date = end
                if loc_override:
                    self._destination = loc_override
                if not self._destination:
                    self._agent_say(
                        "I don't have a default location set. Try something like "
                        "'tomorrow in Paris', or set a default in Settings (⚙)."
                    )
                    return
                self._state = "FETCHING"
                self._fetch_weather()
            except ValueError:
                self._agent_say(
                    "I couldn't read that. Try 'today', 'tomorrow', 'this week', "
                    "or a date like June 10."
                )

        elif self._state == "AWAITING_DESTINATION":
            self._destination = text
            self._state = "AWAITING_START_DATE"
            self._agent_say("What are your travel dates? (e.g. August 1, 2026 or August 1-15, 2026)")

        elif self._state == "AWAITING_START_DATE":
            # Try range first so "August 1-15, 2026" skips the return-date prompt
            try:
                start, end = _parse_date_range(text)
                self._start_date = start
                self._end_date = end
                self._state = "FETCHING"
                self._fetch_weather()
                return
            except ValueError:
                pass
            try:
                self._start_date = _parse_date(text)
                self._state = "AWAITING_END_DATE"
                self._agent_say("And your return date?")
            except ValueError:
                self._agent_say("I couldn't read that date. Try something like August 1, 2026 or August 1-15, 2026.")

        elif self._state == "AWAITING_END_DATE":
            try:
                end = _parse_date(text)
                if end < self._start_date:
                    self._agent_say("Return date must be after departure. Try again.")
                    return
                self._end_date = end
                self._state = "FETCHING"
                self._fetch_weather()
            except ValueError:
                self._agent_say("I couldn't read that date. Try something like August 17, 2026.")

        elif self._state == "CONVERSATION":
            self._busy(True)
            threading.Thread(target=self._call_claude, args=(text,), daemon=True).start()

    # ── Background work ───────────────────────────────────────────────────────

    def _build_user_context(self) -> str:
        parts = []
        work_days = get_work_days()
        dress_code = get_dress_code()
        if work_days:
            parts.append(f"Work/school days: {', '.join(work_days)}")
        if dress_code:
            parts.append(f"Dress code on work/school days: {dress_code}")
        return "\n".join(parts)

    def _fetch_weather(self):
        self._busy(True, "Fetching weather…")
        self._agent_say(f"Fetching weather for {self._destination}…")
        threading.Thread(target=self._do_fetch, daemon=True).start()

    def _do_fetch(self):
        try:
            w = get_weather(
                self._destination,
                self._start_date.isoformat(),
                self._end_date.isoformat(),
            )
            ctx = format_weather_context(w)
            historical = w.get("is_historical", False)
            self.after(0, lambda c=ctx, h=historical: self._weather_ready(c, h))
        except Exception as exc:
            self.after(0, lambda e=exc: self._error(f"Could not fetch weather: {e}"))

    def _weather_ready(self, ctx: str, historical: bool):
        if historical:
            if self._mode == "outfit":
                self._agent_say(
                    "The date is beyond the 16-day forecast window, "
                    "so I'm using historical data from the same period last year."
                )
            else:
                self._agent_say(
                    "Your travel dates are beyond the 16-day forecast window, "
                    "so I'm using historical data from the same period last year."
                )
        self._busy(True)
        user_ctx = self._build_user_context()
        threading.Thread(target=self._do_start, args=(ctx, user_ctx), daemon=True).start()

    def _do_start(self, ctx: str, user_ctx: str = ""):
        try:
            reply, msgs = packer.start_conversation(ctx, mode=self._mode, user_context=user_ctx)
            self._messages = msgs
            self.after(0, lambda r=reply: self._reply(r))
        except Exception as exc:
            self.after(0, lambda e=exc: self._error(f"Could not reach Claude: {e}"))

    def _call_claude(self, user_input: str):
        try:
            reply, msgs = packer.continue_conversation(self._messages, user_input, mode=self._mode)
            self._messages = msgs
            self.after(0, lambda r=reply: self._reply(r))
        except Exception as exc:
            self.after(0, lambda e=exc: self._error(str(e)))

    def _reply(self, text: str):
        self._state = "CONVERSATION"
        self._agent_say(_clean(text))
        self._busy(False)

    def _error(self, msg: str):
        self._agent_say(f"Something went wrong: {msg}")
        self._busy(False)


if __name__ == "__main__":
    if not os.getenv("ANTHROPIC_API_KEY"):
        print("Error: ANTHROPIC_API_KEY is not set.")
        sys.exit(1)
    app = PackingAgentApp()
    app.mainloop()
