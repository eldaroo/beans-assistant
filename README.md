# Supabase SQL Agent

Minimal LangChain SQL Agent for Supabase (PostgreSQL), Python 3.10+.

## Setup
- Create venv: `python -m venv .venv && source .venv/bin/activate` (Windows: `.venv\Scripts\activate`)
- Install deps: `pip install --upgrade pip` then `pip install langchain langchain-openai langchain-community langchain-google-genai psycopg2-binary python-dotenv`
- Configure env: copy `.env.example` to `.env` and fill values. Leave `SUPABASE_DB_OPTIONS` as read-only unless you explicitly need writes; RLS on Supabase still applies.
- Gemini: set `GOOGLE_API_KEY` (or reuse `OPENAI_API_KEY` for compatibility) and `OPENAI_MODEL=gemini-1.5-flash` or `gemini-1.5-pro` (these are supported on the Google Generative AI API). If you prefer the OpenAI-compatible endpoint, set `OPENAI_API_BASE=https://generativelanguage.googleapis.com/openai/v1`.
- Run agent: `python agent.py`

## Notes
- Uses `AgentType.ZERO_SHOT_REACT_DESCRIPTION` with verbose logging for traceability.
- Connection string enforces SSL and read-only by default; Supabase RLS policies remain in effect.
