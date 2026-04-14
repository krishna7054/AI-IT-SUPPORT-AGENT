from __future__ import annotations

import json
import os

from dotenv import load_dotenv


load_dotenv()

ENABLE_GEMINI = os.getenv("ENABLE_GEMINI", "").strip().lower() in {"1", "true", "yes"}
MODEL = None


def _get_model():
    global MODEL
    if MODEL is not None:
        return MODEL
    if not ENABLE_GEMINI:
        raise RuntimeError("Gemini is disabled. Using local parsing and planning.")

    gemini_api_key = os.getenv("GEMINI_API_KEY")
    if not gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY is missing.")

    import google.generativeai as genai

    genai.configure(api_key=gemini_api_key)
    MODEL = genai.GenerativeModel("gemini-3-flash-preview")
    return MODEL


def generate_json(prompt: str) -> dict:
    model = _get_model()
    response = model.generate_content(prompt)
    text = (response.text or "").strip()

    if text.startswith("```"):
        lines = [line for line in text.splitlines() if not line.strip().startswith("```")]
        text = "\n".join(lines).strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Model did not return valid JSON: {text}") from exc
