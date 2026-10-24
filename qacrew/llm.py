"""The LLM the agents use: Groq-hosted models through CrewAI's LiteLLM provider."""

from __future__ import annotations

MODELS = {
    "openai/gpt-oss-120b": "GPT-OSS 120B (best quality)",
    "openai/gpt-oss-20b": "GPT-OSS 20B (faster)",
    "llama-3.3-70b-versatile": "Llama 3.3 70B",
}


# Fields the OpenAI-style chat API accepts on a message. CrewAI 1.x adds its own markers (such as
# "cache_breakpoint" for prompt caching), which Groq rejects with "property ... is unsupported".
MESSAGE_FIELDS = {"role", "content", "name", "tool_calls", "tool_call_id"}


def clean_messages(messages):
    return [{k: v for k, v in m.items() if k in MESSAGE_FIELDS} if isinstance(m, dict) else m for m in messages]


def make_llm(api_key: str, model: str = "openai/gpt-oss-120b"):
    from crewai import LLM

    class GroqLLM(LLM):
        """CrewAI's LiteLLM-backed LLM, sending Groq only the message fields it accepts."""

        def _format_messages_for_provider(self, messages):
            return super()._format_messages_for_provider(clean_messages(messages))

    extra = {"reasoning_effort": "low"} if model.startswith("openai/gpt-oss") else {}
    return GroqLLM(model=f"groq/{model}", api_key=api_key, temperature=0.2, max_tokens=8000, timeout=180,
                   num_retries=3, **extra)


def friendly_error(e: Exception) -> str:
    msg = str(e)
    low = msg.lower()
    if "401" in msg or "invalid_api_key" in low or "invalid api key" in low:
        return "Groq rejected the API key. Check it in the sidebar or in Streamlit secrets."
    if "429" in msg or "rate limit" in low or "rate_limit" in low:
        return ("Groq's rate limit was reached (the free tier allows a limited number of tokens per minute). "
                "Wait a minute, lower 'Maximum requirements', or switch to the 20B model.")
    if "413" in msg or "request too large" in low or "context" in low and "length" in low:
        return "The request was too large for the model. Use a shorter document or lower 'Maximum requirements'."
    return msg[:600]
