from __future__ import annotations

import httpx

from app.config import Settings


class CloudLLMClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @property
    def enabled(self) -> bool:
        return self.settings.cloud_provider == "openai" and bool(self.settings.openai_api_key)

    async def answer(self, refined_prompt: str) -> str:
        if not self.enabled:
            raise RuntimeError("Cloud LLM is not configured")

        url = f"{self.settings.openai_base_url.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.settings.openai_api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.settings.cloud_model,
            "temperature": 0.2,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are the intelligence layer behind a privacy firewall. The user prompt has already been "
                        "sanitized. Do not request exact personal identifiers or confidential values."
                    ),
                },
                {"role": "user", "content": refined_prompt},
            ],
        }
        async with httpx.AsyncClient(timeout=45.0) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
        return data["choices"][0]["message"]["content"].strip()
