from __future__ import annotations

import json

import httpx

from app.config import Settings
from app.models import PrivacyMode


class LocalLLMClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def refine_prompt(self, sanitized_text: str, mode: PrivacyMode) -> tuple[str, bool]:
        instruction = (
            "You are a local privacy refiner. Rewrite the sanitized user request into a clear, compact, "
            "high-signal prompt for an external reasoning model. Never invent identifiers, never restore missing "
            "private details, and preserve the user's underlying intent."
        )
        if mode == PrivacyMode.STRICT:
            instruction += " Generalize further when the request remains overly specific."
        prompt = f"{instruction}\n\nSanitized request:\n{sanitized_text}\n\nRefined prompt:"
        reply = await self._ollama_generate(prompt)
        if reply:
            return reply, True
        return self._deterministic_refinement(sanitized_text, mode), False

    async def answer_locally(self, refined_prompt: str) -> tuple[str, bool]:
        prompt = (
            "You are a fully local assistant operating without external APIs. Provide a helpful answer using only "
            "the sanitized context below. Be honest about uncertainty and avoid asking for specific private details.\n\n"
            f"{refined_prompt}"
        )
        reply = await self._ollama_generate(prompt)
        if reply:
            return reply, True
        fallback = (
            "Local mode is active and no local LLM response was available. The sanitized request is ready, but a local "
            "model such as Mistral 7B via Ollama needs to be running to generate a full answer."
        )
        return fallback, False

    async def generalize_web_query(self, sanitized_text: str) -> tuple[str, bool]:
        prompt = (
            "Rewrite the sanitized request into a short, generic web search query. Keep it under 12 words, remove "
            "private references, and preserve the topic.\n\n"
            f"Sanitized request:\n{sanitized_text}\n\nSearch query:"
        )
        reply = await self._ollama_generate(prompt)
        if reply:
            return reply.strip().splitlines()[0][:120], True
        return self._fallback_web_query(sanitized_text), False

    async def _ollama_generate(self, prompt: str) -> str | None:
        if self.settings.local_llm_provider != "ollama":
            return None
        url = f"{self.settings.ollama_base_url.rstrip('/')}/api/generate"
        payload = {"model": self.settings.local_llm_model, "prompt": prompt, "stream": False}
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                data = response.json()
        except Exception:
            return None
        reply = data.get("response", "")
        return self._strip_prompt_echo(reply)

    def _deterministic_refinement(self, sanitized_text: str, mode: PrivacyMode) -> str:
        framing = "Provide a practical, well-structured response."
        if mode == PrivacyMode.STRICT:
            framing = "Provide a practical response while staying generalized and privacy-preserving."
        return f"{framing}\n\nUser request:\n{sanitized_text}"

    def _fallback_web_query(self, sanitized_text: str) -> str:
        compact = sanitized_text.replace("\n", " ").strip()
        compact = " ".join(compact.split())
        return compact[:120]

    def _strip_prompt_echo(self, reply: str) -> str:
        cleaned = reply.strip()
        if cleaned.startswith("{"):
            try:
                data = json.loads(cleaned)
                if isinstance(data, dict) and "text" in data:
                    return str(data["text"]).strip()
            except Exception:
                return cleaned
        return cleaned
