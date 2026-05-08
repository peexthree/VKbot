# Mindsee Bot

A premium esoteric Telegram/VK bot providing deep personality analysis, tarot readings, and psychological insights.

## Features
- **Tarot Readings:** Daily cards, multi-card spreads, and Grimoire collection.
- **Personality Analysis:** Deep dives into user personas based on birth details.
- **AI-Powered Insights:** Uses advanced LLMs (Gemini/Gemma) for personalized responses.
- **Premium UX:** High-quality image rendering, clean typography, and PDF reports.
- **Roleplay Personas:** Interact with different esoteric characters (e.g., Cyber-Olesya, Ascetic, Oracle).

## Setup

1. **Clone the repository:**
   ```bash
   git clone <repository_url>
   cd mindsee_bot
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Environment Variables:**
   Copy `.env.example` to `.env` and fill in your credentials.
   ```bash
   cp .env.example .env
   ```

4. **Run the bot:**
   ```bash
   python main.py
   ```

## Architecture
- `main.py`: Entry point and task initialization.
- `ai_service.py`: Core AI generation and parsing logic.
- `database.py`: Supabase database interactions.
- `cache.py`: Upstash Redis integration for FSM and caching.
- `modules/`: Organized features (registration, profile, tarot, services, payments, etc.).

## Development
- Uses `vkbottle` for VK API interactions.
- Relies on `loguru` for advanced logging.
- PDF generation via `WeasyPrint` and `Jinja2`.
