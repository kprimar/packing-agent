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

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


def _clean(text: str) -> str:
    """Strip basic markdown so plain text reads cleanly in a label."""
    text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)
    text = re.sub(r"\*(.*?)\*", r"\1", text)
    text = re.sub(r"^#{1,3}\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"^- ", "• ", text, flags=re.MULTILINE)
    return text.strip()


def _parse_date(raw: str):
    formats = [
        "%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y",
        "%B %d %Y", "%b %d %Y", "%B %d, %Y", "%b %d, %Y",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(raw.strip(), fmt).date()
        except ValueError:
            continue
    raise ValueError(raw)


class PackingAgentApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Packing Agent")
        self.geometry("680x740")
        self.minsize(500, 520)

        self._state = "AWAITING_DESTINATION"
        self._destination = None
        self._start_date = None
        self._end_date = None
        self._messages = []

        self._build_ui()
        self.after(150, lambda: self._agent_say("Hi! Where are you traveling to?"))

    # ── Layout ────────────────────────────────────────────────────────────────

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(
            self, text="Packing Agent",
            font=ctk.CTkFont(size=22, weight="bold"),
        ).grid(row=0, column=0, pady=(18, 6))

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
        wrap = max(self.winfo_width() - 220, 300)

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

    # ── Input routing ─────────────────────────────────────────────────────────

    def _on_send(self):
        text = self._entry.get().strip()
        if not text or str(self._btn.cget("state")) == "disabled":
            return
        self._entry.delete(0, "end")
        self._user_say(text)
        self._route(text)

    def _route(self, text: str):
        if self._state == "AWAITING_DESTINATION":
            self._destination = text
            self._state = "AWAITING_START_DATE"
            self._agent_say("What's your departure date? (e.g. 2026-08-01)")

        elif self._state == "AWAITING_START_DATE":
            try:
                self._start_date = _parse_date(text)
                self._state = "AWAITING_END_DATE"
                self._agent_say("And your return date?")
            except ValueError:
                self._agent_say("I couldn't read that date. Try something like 2026-08-01 or August 1, 2026.")

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
                self._agent_say("I couldn't read that date. Try something like 2026-08-17 or August 17, 2026.")

        elif self._state == "CONVERSATION":
            self._busy(True)
            threading.Thread(target=self._call_claude, args=(text,), daemon=True).start()

    # ── Background work ───────────────────────────────────────────────────────

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
            self.after(0, lambda: self._weather_ready(ctx, historical))
        except Exception as exc:
            self.after(0, lambda: self._error(f"Could not fetch weather: {exc}"))

    def _weather_ready(self, ctx: str, historical: bool):
        if historical:
            self._agent_say(
                "Your travel dates are beyond the 16-day forecast window, "
                "so I'm using historical data from the same period last year."
            )
        self._busy(True)
        threading.Thread(target=self._do_start, args=(ctx,), daemon=True).start()

    def _do_start(self, ctx: str):
        try:
            reply, msgs = packer.start_conversation(ctx)
            self._messages = msgs
            self.after(0, lambda: self._reply(reply))
        except Exception as exc:
            self.after(0, lambda: self._error(f"Could not reach Claude: {exc}"))

    def _call_claude(self, user_input: str):
        try:
            reply, msgs = packer.continue_conversation(self._messages, user_input)
            self._messages = msgs
            self.after(0, lambda: self._reply(reply))
        except Exception as exc:
            self.after(0, lambda: self._error(str(exc)))

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
