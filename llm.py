import os
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI

load_dotenv()


def get_llm() -> ChatGoogleGenerativeAI:
    """
    Configure a Gemini chat model using a Google API key.
    Defaults to a supported model (gemini-1.5-flash) and low temperature.
    """
    api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("GOOGLE_API_KEY (or OPENAI_API_KEY) is not set")

    requested_model = (
        os.getenv("OPENAI_MODEL")
        or os.getenv("GEMINI_MODEL")
        or "gemini-2.0-flash-exp"
    )
    # Supported chat models for the Google Generative AI API (generateContent).
    # Note: gemini-1.5-* models have been deprecated in v1beta API as of 2025
    supported_models = {
        "gemini-2.0-flash-exp",
        "gemini-2.5-flash",
        "gemini-2.5-pro",
        "gemini-1.5-flash",  # Legacy support, may not work
        "gemini-1.5-pro",    # Legacy support, may not work
        "gemini-1.5-flash-8b",  # Legacy support, may not work
    }
    model = requested_model if requested_model in supported_models else "gemini-2.0-flash-exp"

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
