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

ctk.set_appearance_mode("light")
ctk.set_default_color_theme("blue")

_BG          = "#ffffff"
_CARD_BG     = "#d9d9d9"
_CARD_BORDER = "#151414"
_AGENT_CLR   = "#c3bde2"
_USER_CLR    = "#77b4ff"
_TEXT        = "#000000"
_BTN_CLR     = "#d9d9d9"
_BTN_HOVER   = "#c4c4c4"
_PH_TEXT     = "Type a message…"
_PH_COLOR    = "#635e5e"


def _clean(text: str) -> str:
    text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)
    text = re.sub(r"\*(.*?)\*", r"\1", text)
    text = re.sub(r"^#{1,3}\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"^- ", "• ", text, flags=re.MULTILINE)
    return text.strip()


_WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


def _parse_date(raw: str):
    import re
    from datetime import date, timedelta

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

    from dateparser.search import search_dates
    hits = search_dates(raw, settings={"PREFER_DATES_FROM": "future", "RETURN_AS_TIMEZONE_AWARE": False})
    if hits:
        return hits[-1][1].date()

    raise ValueError(raw)


def _parse_date_range(raw: str):
    text = raw.strip()

    m = re.match(r"^([A-Za-z]+)\s+(\d{1,2})\s*[-–]\s*(\d{1,2}),?\s*(\d{4})$", text)
    if m:
        month, d1, d2, year = m.group(1), m.group(2), m.group(3), m.group(4)
        return _parse_date(f"{month} {d1}, {year}"), _parse_date(f"{month} {d2}, {year}")

    m = re.match(
        r"^([A-Za-z]+)\s+(\d{1,2})\s*[-–]\s*([A-Za-z]+)\s+(\d{1,2}),?\s*(\d{4})$", text
    )
    if m:
        m1, d1, m2, d2, year = m.group(1), m.group(2), m.group(3), m.group(4), m.group(5)
        return _parse_date(f"{m1} {d1}, {year}"), _parse_date(f"{m2} {d2}, {year}")

    m = re.match(
        r"^([A-Za-z]+)\s+(\d{1,2})\s+to\s+(?:([A-Za-z]+)\s+)?(\d{1,2}),?\s*(\d{4})$",
        text, re.IGNORECASE,
    )
    if m:
        m1, d1, m2, d2, year = (
            m.group(1), m.group(2), m.group(3) or m.group(1), m.group(4), m.group(5)
        )
        return _parse_date(f"{m1} {d1}, {year}"), _parse_date(f"{m2} {d2}, {year}")

    raise ValueError(f"Not a recognizable date range: {raw}")


def _parse_outfit_date_range(raw: str):
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
    from datetime import date as _date
    raw = raw.strip()
    low = raw.lower()

    # Explicit separator: "date in/to location" (case-insensitive)
    for sep in (" in ", " to "):
        if sep in low:
            idx = low.rfind(sep)
            date_part = raw[:idx].strip()
            loc_part = raw[idx + len(sep):].strip()
            # Skip if loc_part starts with a digit — likely a date range ("Feb 2 to 15")
            if date_part and loc_part and not loc_part[0].isdigit():
                try:
                    start, end = _parse_outfit_date_range(date_part)
                    return start, end, loc_part
                except ValueError:
                    pass

    # Implicit: "date location" with no separator — try splitting at each word boundary
    words = raw.split()
    if len(words) >= 2:
        for split_at in range(len(words) - 1, 0, -1):
            date_part = " ".join(words[:split_at])
            loc_part = " ".join(words[split_at:])
            if not loc_part[0].isdigit():
                try:
                    start, end = _parse_outfit_date_range(date_part)
                    return start, end, loc_part
                except ValueError:
                    pass

    # Plain date, no location
    try:
        start, end = _parse_outfit_date_range(raw)
        return start, end, None
    except ValueError:
        pass

    # Input isn't a recognisable date — treat as a location name and use today
    _DATE_WORDS = {
        "today", "tomorrow", "yesterday", "next", "this", "last",
        "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
        "january", "february", "march", "april", "may", "june", "july",
        "august", "september", "october", "november", "december",
        "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep", "oct", "nov", "dec",
        "week", "weekend", "weeks", "day", "days",
    }
    words_low = low.split()
    if words_low and not any(w in _DATE_WORDS for w in words_low) and not words_low[0][0].isdigit():
        return _date.today(), _date.today(), raw

    raise ValueError(raw)


def _parse_outfit_details(raw: str):
    """Parse date, location, and occasion from a single user input.

    Supports inputs like:
      "tomorrow"
      "tomorrow in Tokyo"
      "tomorrow for a work dinner"
      "tomorrow in Tokyo for a business meeting"
      "tokyo"  (location only → date defaults to today)
    Returns (start_date, end_date, location_or_None, occasion_or_None).
    """
    raw = raw.strip()
    low = raw.lower()

    # Split occasion off the end at the last " for "
    occasion = None
    date_loc_str = raw
    for_idx = low.rfind(" for ")
    if for_idx != -1:
        candidate_occasion = raw[for_idx + 5:].strip()
        candidate_date_loc = raw[:for_idx].strip()
        if candidate_occasion and candidate_date_loc:
            occasion = candidate_occasion
            date_loc_str = candidate_date_loc

    if date_loc_str:
        start, end, location = _parse_outfit_date_and_location(date_loc_str)
    else:
        from datetime import date
        start = end = date.today()
        location = None

    return start, end, location, occasion


class PackingAgentApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Packing Agent")
        self.geometry("480x860")
        self.minsize(400, 620)
        self.configure(fg_color=_BG)

        self._mode = None
        self._state = "AWAITING_MODE"
        self._destination = None
        self._start_date = None
        self._end_date = None
        self._outfit_occasion = None
        self._messages = []
        self._ph_active = True
        self._is_busy = False

        self._build_ui()

        if get_default_location():
            self.after(150, self._launch_daily_outfit)
        else:
            self.after(150, lambda: self._agent_say(
                "Hi! I can help you with outfit recommendations for a specific day, "
                "or help you pack for a trip."
            ))

    # ── Layout ─────────────────────────────────────────────────────────────────

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # Header
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=16, pady=(20, 8))
        header.grid_columnconfigure(0, weight=1)

        self._title_lbl = ctk.CTkLabel(
            header, text="Hi there!",
            font=ctk.CTkFont(family="Segoe UI", size=32, weight="bold"),
            text_color=_TEXT, anchor="w",
        )
        self._title_lbl.grid(row=0, column=0, sticky="w")

        ctk.CTkButton(
            header, text="↺", width=40, height=40,
            font=ctk.CTkFont(size=20), corner_radius=20,
            fg_color="transparent", text_color="#434343",
            hover_color="#e8e8e8", command=self._on_refresh,
        ).grid(row=0, column=1, sticky="e", padx=(0, 4))

        ctk.CTkButton(
            header, text="⚙", width=40, height=40,
            font=ctk.CTkFont(size=18), corner_radius=20,
            fg_color="transparent", text_color="#434343",
            hover_color="#e8e8e8", command=self._open_settings,
        ).grid(row=0, column=2, sticky="e")

        # Chat card
        chat_card = ctk.CTkFrame(
            self, fg_color=_CARD_BG, corner_radius=0,
            border_width=2, border_color=_CARD_BORDER,
        )
        chat_card.grid(row=1, column=0, padx=10, pady=(0, 8), sticky="nsew")
        chat_card.grid_columnconfigure(0, weight=1)
        chat_card.grid_rowconfigure(0, weight=1)

        self._chat = ctk.CTkScrollableFrame(chat_card, fg_color="transparent")
        self._chat.grid(row=0, column=0, padx=4, pady=4, sticky="nsew")
        self._chat.grid_columnconfigure(0, weight=1)

        # Bottom section
        self._bottom = ctk.CTkFrame(self, fg_color="transparent")
        self._bottom.grid(row=2, column=0, padx=10, pady=(0, 16), sticky="ew")
        self._bottom.grid_columnconfigure(0, weight=1)

        # Mode buttons frame
        self._mode_frm = ctk.CTkFrame(self._bottom, fg_color="transparent")
        self._mode_frm.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            self._mode_frm, text="Anything else I can help with?",
            font=ctk.CTkFont(size=15), text_color=_TEXT,
        ).grid(row=0, column=0, pady=(4, 10))

        ctk.CTkButton(
            self._mode_frm, text="I need an outfit recommendation",
            height=50, corner_radius=25,
            fg_color=_BTN_CLR, hover_color=_BTN_HOVER,
            text_color=_TEXT, font=ctk.CTkFont(size=14),
            command=lambda: self._click_mode("outfit"),
        ).grid(row=1, column=0, sticky="ew", pady=(0, 8))

        ctk.CTkButton(
            self._mode_frm, text="I need help packing for a trip",
            height=50, corner_radius=25,
            fg_color=_BTN_CLR, hover_color=_BTN_HOVER,
            text_color=_TEXT, font=ctk.CTkFont(size=14),
            command=lambda: self._click_mode("packing"),
        ).grid(row=2, column=0, sticky="ew")

        # Input frame
        self._input_frm = ctk.CTkFrame(self._bottom, fg_color="transparent")
        self._input_frm.grid_columnconfigure(0, weight=1)

        input_card = ctk.CTkFrame(
            self._input_frm, fg_color=_CARD_BG, corner_radius=0,
            border_width=2, border_color=_CARD_BORDER,
        )
        input_card.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        input_card.grid_columnconfigure(0, weight=1)

        self._entry = ctk.CTkTextbox(
            input_card, height=80, font=ctk.CTkFont(size=14),
            fg_color="transparent", text_color=_PH_COLOR,
            border_width=0, wrap="word", activate_scrollbars=False,
        )
        self._entry.grid(row=0, column=0, sticky="ew", padx=10, pady=8)
        self._entry.insert("1.0", _PH_TEXT)
        self._entry.bind("<FocusIn>", self._ph_focus_in)
        self._entry.bind("<FocusOut>", self._ph_focus_out)
        self._entry.bind("<Return>", self._on_enter_key)

        self._btn = ctk.CTkButton(
            self._input_frm, text="Send",
            height=50, corner_radius=25,
            fg_color=_BTN_CLR, hover_color=_BTN_HOVER,
            text_color=_TEXT, font=ctk.CTkFont(size=14),
            command=self._on_send,
        )
        self._btn.grid(row=1, column=0, sticky="ew")

        self._show_mode_buttons()

    def _show_mode_buttons(self):
        self._input_frm.grid_remove()
        self._mode_frm.grid(row=0, column=0, sticky="ew")

    def _show_input(self):
        self._mode_frm.grid_remove()
        self._input_frm.grid(row=0, column=0, sticky="ew")

    def _set_title(self, text: str):
        self._title_lbl.configure(text=text)

    # ── Placeholder ────────────────────────────────────────────────────────────

    def _ph_focus_in(self, _e):
        if self._ph_active:
            self._entry.delete("1.0", "end")
            self._entry.configure(text_color=_TEXT)
            self._ph_active = False

    def _ph_focus_out(self, _e):
        if not self._entry.get("1.0", "end-1c").strip():
            self._entry.insert("1.0", _PH_TEXT)
            self._entry.configure(text_color=_PH_COLOR)
            self._ph_active = True

    def _get_input(self) -> str:
        if self._ph_active:
            return ""
        return self._entry.get("1.0", "end-1c").strip()

    def _clear_input(self):
        self._entry.delete("1.0", "end")
        self._entry.insert("1.0", _PH_TEXT)
        self._entry.configure(text_color=_PH_COLOR)
        self._ph_active = True

    # ── Bubbles ────────────────────────────────────────────────────────────────

    def _agent_say(self, text: str):
        self._bubble(text, is_user=False)

    def _user_say(self, text: str):
        self._bubble(text, is_user=True)

    def _bubble(self, text: str, is_user: bool):
        row = self._chat.grid_size()[1]
        try:
            w_logical = int(self.geometry().split("x")[0])
        except Exception:
            w_logical = 480
        wrap = max(w_logical - 160, 240)

        outer = ctk.CTkFrame(self._chat, fg_color="transparent")
        outer.grid(row=row, column=0, sticky="ew", pady=4, padx=8)
        outer.grid_columnconfigure(0 if is_user else 1, weight=1)

        frame = ctk.CTkFrame(
            outer,
            fg_color=_USER_CLR if is_user else _AGENT_CLR,
            corner_radius=15,
        )
        frame.grid(row=0, column=1 if is_user else 0, sticky="e" if is_user else "w")

        ctk.CTkLabel(
            frame, text=text,
            wraplength=wrap, justify="left", anchor="w",
            text_color=_TEXT, font=ctk.CTkFont(size=13),
        ).pack(padx=14, pady=10)

        self.after(80, self._scroll_bottom)

    def _scroll_bottom(self):
        try:
            self._chat._parent_canvas.yview_moveto(1.0)
        except Exception:
            pass

    # ── Busy state ─────────────────────────────────────────────────────────────

    def _busy(self, on: bool, label: str = "Thinking…"):
        self._is_busy = on
        if on:
            self._btn.configure(text=label, state="disabled")
        else:
            self._btn.configure(text="Send", state="normal")

    # ── Mode selection ─────────────────────────────────────────────────────────

    def _click_mode(self, mode: str):
        if mode == "outfit":
            self._user_say("I need an outfit recommendation")
            self._show_input()
            self._route("outfit")
        else:
            self._user_say("I need help packing for a trip")
            self._show_input()
            self._route("pack")

    # ── Refresh ────────────────────────────────────────────────────────────────

    def _on_refresh(self):
        for widget in self._chat.winfo_children():
            widget.destroy()
        self._mode = None
        self._state = "AWAITING_MODE"
        self._destination = None
        self._start_date = None
        self._end_date = None
        self._outfit_occasion = None
        self._messages = []
        self._is_busy = False
        self._set_title("Hi there!")
        self._clear_input()
        self._show_mode_buttons()
        if get_default_location():
            self.after(150, self._launch_daily_outfit)
        else:
            self.after(150, lambda: self._agent_say(
                "Hi! I can help you with outfit recommendations for a specific day, "
                "or help you pack for a trip."
            ))

    # ── Daily outfit on launch ─────────────────────────────────────────────────

    def _launch_daily_outfit(self):
        from datetime import date, timedelta
        tomorrow = date.today() + timedelta(days=1)
        location = get_default_location()
        self._agent_say(f"Good morning! Let me grab tomorrow's outfit for {location}…")
        threading.Thread(
            target=self._do_daily_outfit, args=(location, tomorrow), daemon=True
        ).start()

    def _do_daily_outfit(self, location, tomorrow):
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
            w = get_weather(location, tomorrow.isoformat(), tomorrow.isoformat())
            ctx = format_weather_context(w)
            if w.get("is_historical"):
                user_context += " (Weather is based on historical data — live forecast unavailable this far out.)"
            reply, _ = packer.get_outfit_email_recommendation(ctx, user_context)
            self.after(0, lambda r=reply: self._agent_say(_clean(r)))
        except Exception as exc:
            self.after(0, lambda e=exc: self._agent_say(f"Could not load daily outfit: {e}"))

    # ── Settings dialog ────────────────────────────────────────────────────────

    def _open_settings(self):
        dialog = ctk.CTkToplevel(self)
        dialog.title("Settings")
        dialog.geometry("440x530")
        dialog.resizable(False, False)
        dialog.configure(fg_color=_BG)
        dialog.grab_set()

        ctk.CTkLabel(
            dialog, text="Settings",
            font=ctk.CTkFont(family="Segoe UI", size=32, weight="bold"),
            text_color=_TEXT, anchor="w",
        ).pack(fill="x", padx=16, pady=(20, 12))

        content = ctk.CTkFrame(dialog, fg_color="transparent")
        content.pack(fill="both", expand=True, padx=16, pady=0)

        # Location
        loc_row = ctk.CTkFrame(content, fg_color="transparent")
        loc_row.pack(fill="x", pady=(0, 4))
        loc_row.grid_columnconfigure(0, weight=1)

        loc_card = ctk.CTkFrame(
            loc_row, fg_color=_CARD_BG, corner_radius=0,
            border_width=2, border_color=_CARD_BORDER,
        )
        loc_card.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        loc_card.grid_columnconfigure(0, weight=1)

        loc_entry = ctk.CTkEntry(
            loc_card, placeholder_text="Enter Location",
            font=ctk.CTkFont(size=14), height=45,
            fg_color="transparent", border_width=0,
            text_color=_TEXT, placeholder_text_color=_PH_COLOR,
        )
        current = get_default_location()
        if current:
            loc_entry.insert(0, current)
        loc_entry.grid(row=0, column=0, sticky="ew", padx=8)

        ctk.CTkButton(
            loc_row, text="Clear", width=80, height=49,
            corner_radius=8,
            fg_color=_BTN_CLR, hover_color=_BTN_HOVER,
            text_color=_TEXT, font=ctk.CTkFont(size=14),
            command=lambda: loc_entry.delete(0, "end"),
        ).grid(row=0, column=1)

        status_lbl = ctk.CTkLabel(
            content, text="", font=ctk.CTkFont(size=12),
            text_color="#cc0000", anchor="w",
        )
        status_lbl.pack(fill="x", pady=(2, 10))

        # Work days
        ctk.CTkLabel(
            content, text="School / Work Days",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=_TEXT, anchor="w",
        ).pack(fill="x", pady=(0, 8))

        days_frame = ctk.CTkFrame(content, fg_color="transparent")
        days_frame.pack(fill="x", pady=(0, 14))
        for col in range(4):
            days_frame.grid_columnconfigure(col, weight=1)

        _SHORT = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        _FULL  = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        saved_days = get_work_days()
        day_vars = {}

        for i, (short, full) in enumerate(zip(_SHORT, _FULL)):
            row_idx = 0 if i < 4 else 1
            col_idx = i if i < 4 else i - 4
            var = ctk.BooleanVar(value=full in saved_days)
            day_vars[full] = var
            cell = ctk.CTkFrame(days_frame, fg_color="transparent")
            cell.grid(row=row_idx, column=col_idx, padx=4, pady=4, sticky="n")
            ctk.CTkLabel(
                cell, text=short, font=ctk.CTkFont(size=13),
                text_color=_TEXT, anchor="center",
            ).pack()
            ctk.CTkCheckBox(
                cell, text="", variable=var,
                width=30, checkbox_width=24, checkbox_height=24,
                corner_radius=3,
                fg_color="#434343", border_color="#434343",
                checkmark_color="#ffffff",
            ).pack(anchor="center", pady=(2, 0))

        # Dress code
        ctk.CTkLabel(
            content, text="School / Work Dress Requirements",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=_TEXT, anchor="w",
        ).pack(fill="x", pady=(0, 8))

        dress_codes = ["Casual", "Business Casual", "Business Formal"]
        saved_code = get_dress_code() or dress_codes[0]
        dress_var = ctk.StringVar(value=saved_code)

        ctk.CTkOptionMenu(
            content, values=dress_codes, variable=dress_var,
            width=300, height=38, font=ctk.CTkFont(size=14),
            fg_color=_BTN_CLR, button_color="#bebdbd",
            button_hover_color=_BTN_HOVER, text_color=_TEXT,
            corner_radius=8,
        ).pack(anchor="w", pady=(0, 18))

        def _save():
            loc = loc_entry.get().strip()
            if loc:
                status_lbl.configure(text="Checking location…")
                dialog.update()
                try:
                    from agent.weather import geocode
                    geocode(loc)
                    set_default_location(loc)
                except Exception:
                    status_lbl.configure(
                        text="Location not found. Try a city name like 'Vancouver' or 'Tokyo'."
                    )
                    return
            else:
                clear_default_location()
            set_work_days([full for full, var in day_vars.items() if var.get()])
            set_dress_code(dress_var.get())
            dialog.destroy()

        ctk.CTkButton(
            content, text="Save",
            height=50, corner_radius=25,
            fg_color=_BTN_CLR, hover_color=_BTN_HOVER,
            text_color=_TEXT, font=ctk.CTkFont(size=14),
            command=_save,
        ).pack(fill="x", pady=(0, 8))

        ctk.CTkButton(
            content, text="Back",
            height=50, corner_radius=25,
            fg_color=_BTN_CLR, hover_color=_BTN_HOVER,
            text_color=_TEXT, font=ctk.CTkFont(size=14),
            command=dialog.destroy,
        ).pack(fill="x")

    # ── Input routing ──────────────────────────────────────────────────────────

    def _on_enter_key(self, event):
        if not (event.state & 0x1):
            self._on_send()
            return "break"

    def _on_send(self):
        if self._is_busy:
            return
        text = self._get_input()
        if not text:
            return
        self._clear_input()
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
                self._set_title("Outfit")
                default = get_default_location()
                self._state = "AWAITING_OUTFIT_DATE"
                if default:
                    self._destination = default
                    self._agent_say(
                        f"What day and occasion? "
                        f"I'll assume {default} unless you say otherwise. "
                        "(e.g. 'tomorrow for a work dinner' or 'Friday in Tokyo for a wedding')"
                    )
                else:
                    self._agent_say(
                        "What day, location, and occasion? "
                        "(e.g. 'tomorrow in Paris for a business meeting') "
                        "Or set a default location in Settings (⚙)."
                    )
            elif any(w in low for w in ("pack", "trip", "travel", "traveling", "travelling")):
                self._mode = "packing"
                self._set_title("Packing")
                self._state = "AWAITING_DESTINATION"
                self._agent_say("Where are you traveling to?")
            else:
                self._agent_say(
                    "I can help with outfit recommendations for a specific day, "
                    "or with packing for a trip. Which would you like?"
                )

        elif self._state == "AWAITING_OUTFIT_DATE":
            try:
                start, end, loc_override, occasion = _parse_outfit_details(text)
                self._start_date = start
                self._end_date = end
                if loc_override:
                    self._destination = loc_override
                self._outfit_occasion = occasion
                if not self._destination:
                    self._agent_say(
                        "I don't have a default location set. Try something like "
                        "'tomorrow in Paris for a dinner', or set a default in Settings (⚙)."
                    )
                    return
                if occasion is None:
                    self._state = "AWAITING_OUTFIT_OCCASION"
                    self._agent_say(
                        "What's the occasion? (e.g. work, a dinner out, casual errands, hiking…)"
                    )
                    return
                self._state = "FETCHING"
                self._proceed_to_fetch()
            except ValueError:
                self._agent_say(
                    "I couldn't read that. Try 'tomorrow for a work dinner', "
                    "'today in Tokyo for a meeting', or a date like 'June 10 for a wedding'."
                )

        elif self._state == "AWAITING_OUTFIT_OCCASION":
            self._outfit_occasion = text.strip()
            self._state = "FETCHING"
            self._proceed_to_fetch()

        elif self._state == "AWAITING_DESTINATION":
            self._destination = text
            self._state = "AWAITING_START_DATE"
            self._agent_say("What are your travel dates? (e.g. August 1, 2026 or August 1-15, 2026)")

        elif self._state == "AWAITING_START_DATE":
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
                self._agent_say(
                    "I couldn't read that date. Try something like August 1, 2026 or August 1-15, 2026."
                )

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

    # ── Background work ────────────────────────────────────────────────────────

    def _build_user_context(self) -> str:
        parts = []
        work_days = get_work_days()
        dress_code = get_dress_code()
        if work_days:
            parts.append(f"Work/school days: {', '.join(work_days)}")
        if dress_code:
            parts.append(f"Dress code on work/school days: {dress_code}")
        if self._mode == "outfit" and self._outfit_occasion:
            parts.append(f"Occasion: {self._outfit_occasion}")
        return "\n".join(parts)

    def _proceed_to_fetch(self):
        """Show extracted params in chat, then start weather fetch.

        Surfaces the parsed {date, location, occasion} so any extraction bug
        is visible before the weather or Claude steps run.
        """
        start, end = self._start_date, self._end_date
        def _fmt(d, include_year=False):
            s = d.strftime("%b %#d")   # %#d = no-padding day on Windows
            if include_year:
                s += f", {d.year}"
            return s

        if start == end:
            date_str = f"{start.strftime('%A')} {_fmt(start)}"
        else:
            date_str = (
                f"{_fmt(start)} – {_fmt(end)}"
                if start.month == end.month
                else f"{_fmt(start)} – {_fmt(end, include_year=True)}"
            )
        parts = [f"Date: {date_str}", f"Location: {self._destination}"]
        if self._outfit_occasion:
            parts.append(f"Occasion: {self._outfit_occasion}")
        self._agent_say("\n".join(parts))
        self._fetch_weather()

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
