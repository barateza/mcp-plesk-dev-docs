import json
import logging
import os
import re
from typing import List, Optional

import requests

logger = logging.getLogger(__name__)

DEFAULT_MODELS = [
    "arcee-ai/trinity-large-preview:free",
    "stepfun/step-3-5-flash:free",
    "liquid/lfm-2.5-1.2b-thinking:free",
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
                    return response.json()["choices"][0]["message"]["content"].strip()
            except Exception as e:
                logger.debug(f"Answer Model {model} failed with exception: {e}")
                continue

        return "Error generating answer."

    def generate_description(
        self, text: str, model_list: Optional[List[str]] = None
    ) -> str:
        """
        Attempts to get a description using a tiered fallback system.
        """
        if not text.strip():
            return "File unreadable."

        models = model_list if model_list is not None else DEFAULT_MODELS

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
                    return response.json()["choices"][0]["message"]["content"].strip()
                else:
                    logger.debug(
                        f"Model {model} returned status {response.status_code}"
                    )
            except Exception as e:
                logger.debug(f"Model {model} failed with exception: {e}")
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
                    text = response.json()["choices"][0]["message"]["content"].strip()
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
