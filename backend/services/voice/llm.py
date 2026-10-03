import os
import re
import time
import logging
from typing import Any
from groq import AsyncGroq
from openai import AsyncOpenAI

logger = logging.getLogger("voice.llm")

SARVAM_LLM_BASE_URL = "https://api.sarvam.ai/v1"
CEREBRAS_LLM_BASE_URL = "https://api.cerebras.ai/v1"
GEMINI_LLM_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
TOGETHER_LLM_BASE_URL = "https://api.together.xyz/v1"

FALLBACK_MODEL = "llama-3.1-8b-instant"


class LLMService:
    """Manages LLM client configuration, multi-provider fallbacks, and streaming generation."""

    def __init__(self):
        self.fallback_model = FALLBACK_MODEL

    def get_client_and_model(self) -> tuple[Any, str, int, str]:
        """Selects the active LLM client, model name, max tokens, and provider name."""
        together_key = os.getenv("TOGETHER_API_KEY")
        gemini_key = os.getenv("GEMINI_API_KEY")
        cerebras_key = os.getenv("CEREBRAS_API_KEY")
        sarvam_key = os.getenv("SARVAM_API_KEY")
        groq_key = os.getenv("GROQ_API_KEY")
        llm_provider = os.getenv("LLM_PROVIDER", "groq").lower()

        if llm_provider == "together" and together_key:
            client = AsyncOpenAI(base_url=TOGETHER_LLM_BASE_URL, api_key=together_key, max_retries=0)
            model_name = os.getenv("TOGETHER_LLM_MODEL", "meta-llama/Llama-3.3-70B-Instruct-Turbo")
            return client, model_name, 400, "together"
        elif llm_provider == "gemini" and gemini_key:
            client = AsyncOpenAI(base_url=GEMINI_LLM_BASE_URL, api_key=gemini_key, max_retries=0)
            model_name = os.getenv("GEMINI_LLM_MODEL", "gemini-flash-lite-latest")
            return client, model_name, 400, "gemini"
        elif llm_provider == "cerebras" and cerebras_key:
            client = AsyncOpenAI(base_url=CEREBRAS_LLM_BASE_URL, api_key=cerebras_key, max_retries=0)
            model_name = os.getenv("CEREBRAS_LLM_MODEL", "zai-glm-4.7")
            return client, model_name, 400, "cerebras"
        elif llm_provider == "sarvam" and sarvam_key:
            client = AsyncOpenAI(base_url=SARVAM_LLM_BASE_URL, api_key=sarvam_key, max_retries=0)
            model_name = os.getenv("SARVAM_LLM_MODEL", "sarvam-30b")
            return client, model_name, 1600, "sarvam"
        else:
            client = AsyncGroq(api_key=groq_key, max_retries=0)
            model_name = os.getenv("GROQ_LLM_MODEL", "llama-3.1-8b-instant")
            return client, model_name, 400, "groq"

    async def create_chat_stream(
        self,
        client: Any,
        model_name: str,
        messages: list[dict],
        max_tokens: int,
        provider: str,
    ) -> tuple[Any, str]:
        """Initiates the LLM completion stream with automatic multi-provider fallback."""
        sarvam_key = os.getenv("SARVAM_API_KEY")
        groq_key = os.getenv("GROQ_API_KEY")

        logger.info(f"[LLM] Calling model {model_name}...")
        try:
            stream = await client.chat.completions.create(
                model=model_name,
                messages=messages,
                temperature=0.75,
                max_tokens=max_tokens,
                stream=True,
            )
            return stream, model_name
        except Exception as llm_err:
            err_str = str(llm_err)
            if sarvam_key and provider != "sarvam":
                fallback_sarvam_model = os.getenv("SARVAM_LLM_MODEL", "sarvam-30b")
                logger.warning(
                    f"[LLM] Primary model error: {err_str}. Falling back to Sarvam {fallback_sarvam_model}..."
                )
                sarvam_client = AsyncOpenAI(base_url=SARVAM_LLM_BASE_URL, api_key=sarvam_key, max_retries=0)
                stream = await sarvam_client.chat.completions.create(
                    model=fallback_sarvam_model,
                    messages=messages,
                    temperature=0.7,
                    max_tokens=1600,
                    stream=True,
                )
                return stream, fallback_sarvam_model
            else:
                logger.warning(
                    f"[LLM] Primary model '{model_name}' error: {err_str}. Retrying with {self.fallback_model} on Groq..."
                )
                groq_client2 = AsyncGroq(api_key=groq_key, max_retries=0)
                stream = await groq_client2.chat.completions.create(
                    model=self.fallback_model,
                    messages=messages,
                    temperature=0.7,
                    max_tokens=400,
                    stream=True,
                )
                return stream, self.fallback_model

    def update_history(self, session_state: dict, transcript: str, system_prompt: str) -> list[dict]:
        """Prepares and truncates conversation history."""
        history = session_state.get("history", [])
        if not history or history[0].get("role") != "system":
            history.insert(0, {"role": "system", "content": system_prompt})
        else:
            history[0] = {"role": "system", "content": system_prompt}

        history.append({"role": "user", "content": transcript})
        if len(history) > 7:
            history = [history[0]] + history[-6:]
        session_state["history"] = history
        return history
