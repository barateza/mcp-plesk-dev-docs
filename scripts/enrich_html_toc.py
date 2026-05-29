#!/usr/bin/env python3
"""
Enrich HTML documentation TOC nodes with AI-generated descriptions.

Reads existing toc.json files from knowledge_base/guide-dirs and generates
concise one-sentence summaries for nodes that lack them, using a local
LLM (LM Studio / Ollama) or OpenRouter as fallback.

Usage:
    python scripts/enrich_html_toc.py
    python scripts/enrich_html_toc.py --guide extensions-guide,api-rpc

The enriched toc.json is written back in-place. The server's own
indexing pipeline (io_utils.py → chunking.py) handles downloading,
extracting, and converting; this script only adds metadata.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import requests
from bs4 import BeautifulSoup

# --- Configuration ---

USE_LOCAL_LLM = True
LOCAL_API_URL = "http://localhost:1234/v1"
LOCAL_MODEL_ID = "llama-3.1-8b-instruct"

OPENROUTER_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = "liquid/lfm-2.5-1.2b-thinking:free"

KB_DIR = Path(__file__).parent.parent / "knowledge_base"

# Guides whose toc.json should be enriched
DEFAULT_GUIDES = [
    "extensions-guide",
    "cli-linux",
    "api-rpc",
]

# --- Helpers ---


def clean_llm_response(text: str) -> str:
    """Trim conversational filler from LLM output."""
    text = text.strip().strip('"').strip("'")
    garbage_prefixes = [
        "Here is a concise sentence summarizing",
        "Here is a concise sentence",
        "Here is a summary",
        "The technical purpose of the file is to",
        "The technical purpose of the file",
        "The technical purpose of this file",
        "In this section, the documentation",
        "This section",
        "concise sentence:",
        "Summary:",
        "Description:",
    ]
    for prefix in garbage_prefixes:
        if text.lower().startswith(prefix.lower()):
            if ":" in text:
                text = text.split(":", 1)[1]
            else:
                text = text[len(prefix) :]
    text = text.strip()
    if text.lower().startswith("titled") and ":" in text:
        text = text.split(":", 1)[1]
    return text.strip()


def generate_description(
    filename: str, section_title: str, content_snippet: str
) -> str:
    """Generate a one-sentence description for a TOC node via LLM."""
    prompt = (
        "You are a technical indexer.\n"
        f"Context: The file '{filename}' contains documentation for Plesk.\n"
        "Task: Write exactly one concise sentence summarizing the specific section "
        f"titled '{section_title}'.\n"
        "Rules:\n"
        "1. Start directly with a verb (e.g., 'Explains', 'Defines', 'Configures').\n"
        "2. Do NOT say 'Here is a summary'.\n"
        "3. Do NOT mention the filename.\n"
        "4. Focus ONLY on the section.\n\n"
        "Content Snippet:\n" + content_snippet[:3500]
    )
    messages = [
        {
            "role": "system",
            "content": (
                "You are a precise technical documenter. Output only the summary."
            ),
        },
        {"role": "user", "content": prompt},
    ]

    try:
        if USE_LOCAL_LLM:
            resp = requests.post(
                f"{LOCAL_API_URL}/chat/completions",
                json={
                    "model": LOCAL_MODEL_ID,
                    "messages": messages,
                    "temperature": 0.1,
                    "max_tokens": 80,
                    "stream": False,
                },
                timeout=60,
            )
            if resp.status_code != 200:
                print(f"[!] Local LLM Error: {resp.text}")
                return ""
            raw = resp.json()["choices"][0]["message"]["content"]
            return clean_llm_response(raw)
        else:
            resp = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENROUTER_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": OPENROUTER_MODEL,
                    "messages": messages,
                    "max_tokens": 100,
                },
                timeout=15,
            )
            if resp.status_code == 200:
                return clean_llm_response(
                    resp.json()["choices"][0]["message"]["content"]
                )
            return ""
    except Exception as e:
        print(f"[!] AI Generation Exception: {e}")
        return ""


def node_needs_description(node: dict) -> bool:
    desc = node.get("description", "")
    if not desc:
        return True
    if "concise sentence" in desc or "Here is a summary" in desc:
        return True
    return False


def process_toc_nodes(nodes: list[dict], action) -> int:
    count = 0
    for node in nodes:
        if action(node):
            count += 1
        if "children" in node:
            count += process_toc_nodes(node["children"], action)
    return count


def enrich_guide(guide_name: str) -> int:
    """Enrich one guide's toc.json. Returns number of descriptions updated."""
    toc_path = KB_DIR / guide_name / "toc.json"
    html_dir = KB_DIR / guide_name / "html"

    if not toc_path.exists():
        print(f"[!] No toc.json at {toc_path}. Skipping.")
        return 0
    if not html_dir.exists():
        print(f"[!] No html dir at {html_dir}. Skipping.")
        return 0

    with open(toc_path, "r", encoding="utf-8") as f:
        toc = json.load(f)

    updated = [0]  # mutable counter for the closure

    def action(node: dict) -> bool:
        if not node_needs_description(node):
            return False
        if "url" not in node or ".htm" not in node["url"]:
            return False

        filename = node["url"].split("#")[0]
        file_path = html_dir / filename
        if not file_path.exists():
            return False

        try:
            text = file_path.read_text(encoding="utf-8", errors="ignore")
            text_clean = BeautifulSoup(text, "html.parser").get_text()
        except Exception as e:
            print(f"    ! Error reading {filename}: {e}")
            return False

        section_title = node.get("text", "this section")
        print(f"    > Generating summary for: '{section_title}'")
        new_desc = generate_description(filename, section_title, text_clean)

        if new_desc:
            node["description"] = new_desc
            updated[0] += 1
            if updated[0] % 5 == 0:
                with open(toc_path, "w", encoding="utf-8") as f:
                    json.dump(toc, f, indent=2)
            return True
        return False

    total = process_toc_nodes(toc, action)

    if total > 0:
        with open(toc_path, "w", encoding="utf-8") as f:
            json.dump(toc, f, indent=2)
        print(f"[+] {guide_name}: updated {total} descriptions.")
    else:
        print(f"[-] {guide_name}: no new descriptions needed.")

    return total


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Enrich HTML TOC nodes with AI descriptions"
    )
    parser.add_argument(
        "--guides",
        type=str,
        default=",".join(DEFAULT_GUIDES),
        help="Comma-separated guide dirs to enrich (default: all)",
    )
    args = parser.parse_args()

    guides = [g.strip() for g in args.guides.split(",") if g.strip()]

    if USE_LOCAL_LLM:
        try:
            requests.get(f"{LOCAL_API_URL}/models", timeout=2)
        except Exception:
            print("[!] Warning: Could not connect to LM Studio. Enrichment will fail.")

    total = 0
    for guide in guides:
        print(f"\n=== Enriching {guide} ===")
        total += enrich_guide(guide)

    print(f"\nDone. {total} descriptions updated across {len(guides)} guides.")


if __name__ == "__main__":
    main()
