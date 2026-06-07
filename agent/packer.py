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


SYSTEM_PROMPT = """\
You are a practical and knowledgeable travel packing assistant. Your goal is to help the user pack the right amount of clothing — enough to be comfortable, but not so much that they're lugging around a heavy bag unnecessarily.

You will be given weather data for the user's destination and travel dates. Use it to inform all of your recommendations.

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


def start_conversation(weather_context: str) -> tuple[str, list]:
    """
    Send the first message to Claude (weather context + request for initial recommendation).
    Returns (assistant_reply, messages_history).
    """
    client = get_client()

    messages = [
        {
            "role": "user",
            "content": (
                "Here is the weather data for my trip:\n\n"
                f"{weather_context}\n\n"
                "Please give me your initial packing recommendation."
            ),
        }
    ]

    response = client.messages.create(
        model="claude-opus-4-7",
        max_tokens=1024,
        system=[
            {
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=messages,
    )

    reply = response.content[0].text
    messages.append({"role": "assistant", "content": reply})
    return reply, messages


def continue_conversation(messages: list, user_input: str) -> tuple[str, list]:
    """
    Send the user's next message and get the assistant's reply.
    Returns (assistant_reply, updated_messages_history).
    """
    client = get_client()

    messages = messages + [{"role": "user", "content": user_input}]

    response = client.messages.create(
        model="claude-opus-4-7",
        max_tokens=1024,
        system=[
            {
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=messages,
    )

    reply = response.content[0].text
    messages.append({"role": "assistant", "content": reply})
    return reply, messages
