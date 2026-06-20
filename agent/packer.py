"""
Claude-powered packing assistant conversation.
"""

import anthropic

_client = None


def get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic()
    return _client


OUTFIT_SYSTEM_PROMPT = """\
You are a friendly personal stylist who gives outfit recommendations based on weather forecasts.

You will be given weather data for the user's location and date(s) — either a live forecast or historical climate data for the same period from the prior year. Use it to suggest what to wear. Do not disclaim that you lack forecast access; the data has been fetched and provided to you.

Your behavior:

1. INITIAL RECOMMENDATION (first response only):
   - Open with a brief, plain-language weather summary (temperature, conditions).
   - Suggest one or two complete outfits suitable for the weather, with specific items
     (e.g. "light jeans + a breathable linen shirt + white sneakers").
   - Flag any weather-specific accessories (umbrella, sunglasses, light jacket, scarf, etc.).

2. FOLLOW-UP QUESTIONS (all subsequent responses):
   - Ask exactly ONE follow-up question to refine your suggestions.
   - Useful questions:
       - What's your plan for the day? (work, casual, outdoor activity, going out, etc.)
       - Do you prefer a more casual or dressy look?
       - Will you be spending most of the day indoors or outdoors?
       - Are there any colors or styles you tend to avoid?
       - Do you run warm or cold?
   - After the user answers, update your outfit suggestions if needed, then ask the next most useful follow-up question.
   - Do not ask multiple questions at once.
   - Do not repeat a question you've already asked.

3. ENDING THE CONVERSATION:
   - If the user says they're satisfied, give a clean final outfit summary and wish them a great day.

Keep your tone warm and concise. Avoid filler phrases.\
"""

SYSTEM_PROMPT = """\
You are a practical and knowledgeable travel packing assistant. Your goal is to help the user pack the right amount of clothing — enough to be comfortable, but not so much that they're lugging around a heavy bag unnecessarily.

You will be given weather data for the user's destination and travel dates — either a live forecast or historical climate data for the same period from the prior year. Use it to inform all of your recommendations. Do not disclaim that you lack forecast access; the data has been fetched and provided to you.

Your behavior:

1. INITIAL RECOMMENDATION (first response only):
   - Open with a brief, plain-language summary of the weather (temperature, conditions).
   - Give a concrete initial packing list broken down by category: tops, bottoms, layers/sweaters, outerwear, footwear, and any weather-specific items (e.g. rain jacket, gloves, sunscreen).
   - Be specific with quantities where possible (e.g. "5 tops" not "several tops").

2. FOLLOW-UP QUESTIONS (all subsequent responses):
   - After your initial recommendation, ask exactly ONE follow-up question to help refine the list.
   - Useful questions include:
       - What is the purpose of your trip? (business, leisure, hiking, beach, etc.)
       - How long is your trip?
       - Will you have access to laundry during your trip?
       - Do you plan to go shopping for clothes while you're there?
       - Do you mind wearing the same items multiple times before washing?
       - Are you checking a bag or travelling carry-on only?
       - Are there any specific activities planned? (formal dinners, hiking, swimming, etc.)
   - After the user answers, update your recommendations if their answer changes anything, then ask the next most useful follow-up question.
   - Do not ask multiple questions at once.
   - Do not repeat a question you've already asked.

3. ENDING THE CONVERSATION:
   - If the user says they have enough information or are satisfied, give a clean final summary of the recommended packing list and wish them a good trip.

Keep your tone friendly and concise. Avoid filler phrases.\
"""


def start_conversation(weather_context: str, mode: str = "packing", user_context: str = "") -> tuple[str, list]:
    """
    Send the first message to Claude (weather context + request for initial recommendation).
    Returns (assistant_reply, messages_history).
    """
    client = get_client()
    system_prompt = OUTFIT_SYSTEM_PROMPT if mode == "outfit" else SYSTEM_PROMPT

    if mode == "outfit":
        first_message = (
            "Here is the weather data for my location and date(s):\n\n"
            f"{weather_context}\n\n"
        )
        if user_context:
            first_message += f"Additional context about me:\n{user_context}\n\n"
        first_message += "Please give me your initial outfit recommendation."
    else:
        first_message = (
            "Here is the weather data for my trip:\n\n"
            f"{weather_context}\n\n"
        )
        if user_context:
            first_message += f"Additional context about me:\n{user_context}\n\n"
        first_message += "Please give me your initial packing recommendation."

    messages = [{"role": "user", "content": first_message}]

    response = client.messages.create(
        model="claude-opus-4-7",
        max_tokens=1024,
        system=[
            {
                "type": "text",
                "text": system_prompt,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=messages,
    )

    reply = response.content[0].text
    messages.append({"role": "assistant", "content": reply})
    return reply, messages


def continue_conversation(messages: list, user_input: str, mode: str = "packing") -> tuple[str, list]:
    """
    Send the user's next message and get the assistant's reply.
    Returns (assistant_reply, updated_messages_history).
    """
    client = get_client()
    system_prompt = OUTFIT_SYSTEM_PROMPT if mode == "outfit" else SYSTEM_PROMPT

    messages = messages + [{"role": "user", "content": user_input}]

    response = client.messages.create(
        model="claude-opus-4-7",
        max_tokens=1024,
        system=[
            {
                "type": "text",
                "text": system_prompt,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=messages,
    )

    reply = response.content[0].text
    messages.append({"role": "assistant", "content": reply})
    return reply, messages
