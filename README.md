# Voice-to-Swiggy Multi-Modal Agent

An intelligent, multi-modal voice and text agent built for the Swiggy ecosystem. The platform leverages Deepmind models and native Telegram & WebApp integrations to provide a seamless ordering experience.

## Overview
This platform acts as a smart wrapper around the Swiggy ordering process. Instead of navigating menus manually, users can simply speak or text their cravings. The agent autonomously parses the intent (Food Delivery, Instamart, or Dineout), prompts for missing details like location and quantity, and confirms the mock order.

## Architecture & Tech Stack
* **Frontend:** Vanilla HTML/CSS/JS with a responsive, mobile-first WebApp. Features native Web Audio recording and Telegram Bottom Sheet integrations.
* **Backend:** Flask and Gunicorn for managing Telegram webhooks and WebApp API endpoints.
* **Agentic Orchestration:** `swiggy_agent.py` drives the state machine.
* **LLM Engine:** Dynamic fallback architecture prioritizing Groq (Llama-3), OpenRouter, HuggingFace, and Gemini to ensure 100% uptime and bypass 429 quota errors.
* **Observability:** Custom `logger_store.py` and `network_store.py` for intercepting and logging LLM/API traces, visible in an internal APIGW Dashboard (`/admin/apigw`).

## Setup & Deployment

1. **Clone the repository**
2. **Install requirements:** `pip install -r requirements.txt`
3. **Set Environment Variables:**
   * `TELEGRAM_BOT_TOKEN`: Your Telegram Bot API Token.
   * `ADMIN_SECRET`: Secret to access the APIGW Dashboard.
   * `GROQ_API_KEY`, `OPENROUTER_API_KEY`, `HUGGINGFACE_API_KEY`, `GEMINI_API_KEY`, `OPENAI_API_KEY`: Keys for the fallback logic.

4. **Run Locally:**
   ```bash
   gunicorn -w 1 -b 0.0.0.0:8000 app:app
   ```

## Key Features
* **Native Authentication:** Integrates a mobile-friendly OTP Bottom Sheet (`000000` for mock login) alongside Telegram's native Contact Sharing.
* **Address Menu Logic:** Automatically fetches and prompts the user with saved mock addresses (Aryan Apartments, Tulsi Vihar) for Instamart and Food delivery requests.
* **Session Persistence:** State-aware memory clears itself natively using a `[SESSION_FINISHED]` hidden flag when an order is finalized.