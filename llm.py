import os
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI

load_dotenv()


def get_llm() -> ChatGoogleGenerativeAI:
    """
    Configure a Gemini chat model using a Google API key.
    Defaults to a supported model (gemini-2.5-flash) and low temperature.
    """
    api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("GOOGLE_API_KEY (or OPENAI_API_KEY) is not set")

    requested_model = (
        os.getenv("OPENAI_MODEL")
        or os.getenv("GEMINI_MODEL")
        or "gemini-2.5-flash"
    )
    # Supported chat models for the Google Generative AI API (generateContent).
    supported_models = {
        "gemini-2.5-flash",
        "gemini-2.5-pro",
        "gemini-2.0-flash-exp",  # Legacy support, may not work in some API versions
    }
    model = requested_model if requested_model in supported_models else "gemini-2.5-flash"

    print(f"DEBUG: Requested model: {requested_model}")
    print(f"DEBUG: Using model: {model}")

    temperature = float(
        os.getenv("OPENAI_TEMPERATURE")
        or os.getenv("GEMINI_TEMPERATURE")
        or "0.2"
    )

    return ChatGoogleGenerativeAI(
        model=model,
        temperature=temperature,
        google_api_key=api_key,
    )


def get_llm_cheap() -> ChatGoogleGenerativeAI:
    """
    Get a fast LLM for simple tasks like disambiguation.
    Defaults to gemini-2.5-flash unless GEMINI_CHEAP_MODEL is set.

    Returns:
        ChatGoogleGenerativeAI configured for cheap operations
    """
    api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("GOOGLE_API_KEY (or OPENAI_API_KEY) is not set")

    # Prefer a broadly available fast model to avoid runtime NOT_FOUND errors.
    model = os.getenv("GEMINI_CHEAP_MODEL", "gemini-2.5-flash")

    return ChatGoogleGenerativeAI(
        model=model,
        temperature=0.1,  # Low temperature for disambiguation
        google_api_key=api_key,
    )
