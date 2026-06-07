# Packing Agent

A CLI tool that recommends what to pack for a trip based on real weather data and a conversational follow-up flow powered by Claude.

## How it works

1. You enter your destination and travel dates
2. The agent fetches weather data for that location and period (via [Open-Meteo](https://open-meteo.com/), free, no API key required)
3. Claude gives an initial packing recommendation with specific quantities
4. The agent asks follow-up questions one at a time — trip purpose, laundry access, bag type, planned activities, etc. — and refines the list as you answer
5. Type `done` when you have enough information

## Setup

```powershell
cd packing-agent
.\setup.ps1
.\.venv\Scripts\Activate.ps1
```

Set your Anthropic API key:

```powershell
$env:ANTHROPIC_API_KEY = "sk-..."
```

## Usage

```powershell
python main.py
```

You'll be prompted for a destination and travel dates (YYYY-MM-DD). The agent handles the rest.

**Weather notes:**
- Travel dates within the next 16 days use live forecast data
- Dates further out use historical data from the same period last year as an approximation

## Requirements

- Python 3.10+
- An [Anthropic API key](https://console.anthropic.com/)
