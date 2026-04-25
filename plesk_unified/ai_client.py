import json
import logging
import os
import re
from typing import List, Optional

import requests
import httpx

logger = logging.getLogger(__name__)

DEFAULT_MODELS = [
    "deepseek/deepseek-v4-flash",
    "google/gemini-2.5-flash-lite",
    "x-ai/grok-4.1-fast",
    "nvidia/nemotron-3-super-120b-a12b:free",
]

# RAGAS judge model — chosen for instruction-following + low verbosity on strict
# "Score 0.0–1.0" tasks.
RAGAS_DEFAULT_MODELS = [
    "google/gemini-2.0-flash",
    "anthropic/claude-3-haiku",
]


class AIClient:
    """A thin wrapper for LLM calls with retry/fallback policy."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get("OPENROUTER_API_KEY", "")
        if not self.api_key:
            logger.warning("OPENROUTER_API_KEY is not set. AI calls will fail.")
        else:
            logger.info("AIClient initialized with an API key.")
        self._async_client: Optional[httpx.AsyncClient] = None

    async def get_async_client(self) -> httpx.AsyncClient:
        if self._async_client is None or self._async_client.is_closed:
            self._async_client = httpx.AsyncClient(timeout=30.0)
        return self._async_client

    async def close(self):
        if self._async_client and not self._async_client.is_closed:
            await self._async_client.aclose()

    def generate_answer(
        self, query: str, context: str, model_list: Optional[List[str]] = None
    ) -> str:
        """
        Generate an answer to the query based strictly on the provided context.
        """
        models = model_list if model_list is not None else DEFAULT_MODELS

        for model in models:
            try:
                content = (
                    f"CONTEXT:\n{context}\n\n"
                    f"QUERY: {query}\n\n"
                    "Answer the query based ONLY on the provided context. "
                    "If the information is not present, say 'Information not found'."
                )

                payload = {
                    "model": model,
                    "messages": [{"role": "user", "content": content}],
                    "max_tokens": 500,
                }

                logger.debug(f"Sending request to model {model} (answer generation)")
                response = requests.post(
                    url="https://openrouter.ai/api/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    data=json.dumps(payload),
                    timeout=20,
                )
                if response.status_code == 200:
                    data = response.json()
                    choices = data.get("choices")
                    if choices and "message" in choices[0]:
                        res = choices[0]["message"].get("content")
                        if res:
                            return res.strip()

                logger.error(
                    f"Model {model} returned status {response.status_code}: "
                    f"{response.text[:200]}"
                )
            except Exception as e:
                logger.error(f"Answer Model {model} failed with exception: {e}")
                continue

        return "Error generating answer."

    async def generate_description_async(
        self, text: str, model_list: Optional[List[str]] = None
    ) -> str:
        """
        Attempts to get a description using a tiered fallback system (Asynchronous).
        """
        if not text.strip():
            return "File unreadable."

        models = model_list if model_list is not None else DEFAULT_MODELS
        client = await self.get_async_client()

        for model in models:
            try:
                content = (
                    "Summarize the technical purpose of the following text "
                    "in exactly one concise sentence.\n\n" + text
                )

                payload = {
                    "model": model,
                    "messages": [{"role": "user", "content": content}],
                    "max_tokens": 100,
                }

                # Force DeepSeek provider for deepseek models
                # to avoid slow providers like deepinfra
                if "deepseek" in model:
                    payload["provider"] = {"order": ["DeepSeek"]}

                response = await client.post(
                    url="https://openrouter.ai/api/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
                if response.status_code == 200:
                    data = response.json()
                    choices = data.get("choices")
                    if choices and "message" in choices[0]:
                        res = choices[0]["message"].get("content")
                        if res:
                            return res.strip()

                logger.error(
                    f"Model {model} returned status {response.status_code}: "
                    f"{response.text[:200]}"
                )
            except Exception as e:
                logger.error(f"Model {model} failed with exception: {e}")
                continue

        return "Description unavailable."

    def generate_description(
        self, text: str, model_list: Optional[List[str]] = None
    ) -> str:
        """
        Attempts to get a description using a tiered fallback system.
        """
        if not text.strip():
            return "File unreadable."

        models = model_list if model_list is not None else DEFAULT_MODELS

        logger.info(f"AIClient.generate_description called for text length {len(text)}")
        for model in models:
            try:
                content = (
                    "Summarize the technical purpose of the following text "
                    "in exactly one concise sentence.\n\n" + text
                )

                payload = {
                    "model": model,
                    "messages": [{"role": "user", "content": content}],
                    "max_tokens": 100,
                }

                logger.info(f"Sending description request to model {model}")
                response = requests.post(
                    url="https://openrouter.ai/api/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    data=json.dumps(payload),
                    timeout=15,
                )
                if response.status_code == 200:
                    data = response.json()
                    choices = data.get("choices")
                    if choices and "message" in choices[0]:
                        res = choices[0]["message"].get("content")
                        if res:
                            logger.info(
                                f"Successfully generated description using {model}"
                            )
                            return res.strip()

                logger.error(
                    f"Model {model} returned status {response.status_code}: "
                    f"{response.text[:200]}"
                )
            except Exception as e:
                logger.error(f"Model {model} failed with exception: {e}")
                continue

        return "Description unavailable."

    def evaluate_ragas_score(
        self, prompt: str, model_list: Optional[List[str]] = None
    ) -> float:
        """
        Evaluate a RAGAS metric prompt and return a score between 0.0 and 1.0.
        Uses stricter instruction following for the judge model.
        """
        models = model_list if model_list is not None else RAGAS_DEFAULT_MODELS

        for model in models:
            try:
                payload = {
                    "model": model,
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                "You are a precise evaluator. Output ONLY a single "
                                "float number between 0.0 and 1.0 representing the "
                                "score. No explanation, no extra text."
                            ),
                        },
                        {"role": "user", "content": prompt},
                    ],
                    "max_tokens": 10,
                }

                response = requests.post(
                    url="https://openrouter.ai/api/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    data=json.dumps(payload),
                    timeout=20,
                )
                if response.status_code == 200:
                    data = response.json()
                    choices = data.get("choices")
                    if choices and "message" in choices[0]:
                        msg = choices[0]["message"]
                        text = msg.get("content", "").strip()
                        # Try to find a float in the response
                        match = re.search(r"(\d?\.\d+)", text)
                        if match:
                            return float(match.group(1))
                        if text in ["0", "1"]:
                            return float(text)
                else:
                    logger.debug(
                        f"RAGAS Model {model} returned status {response.status_code}"
                    )
            except Exception as e:
                logger.debug(f"RAGAS Model {model} failed with exception: {e}")
                continue

        return 0.0
