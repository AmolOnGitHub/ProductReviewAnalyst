from __future__ import annotations
import json
from typing import Any, Dict

from google.genai import types
from src.llm.gemini_client import get_client, MODEL_NAME

SYSTEM_INSTRUCTION = """
You are an analytics assistant.

You MUST:
- Answer ONLY using the provided tool results.
- Not invent facts or categories.
- Be concise, clear, and professional.
- If the data does not show clear or recurring issues, explicitly state that feedback is overwhelmingly positive. In that case, summarize the most common positive reasons instead of issues. 
- Do not invent problems.

Do NOT mention tools, routing, or implementation details.
Do NOT output JSON. Output plain text only.
"""

def write_response(
    *,
    user_message: str,
    tool_name: str,
    tool_args: Dict[str, Any],
    tool_result: Dict[str, Any],
    recent_messages: list[dict],
) -> str:
    client = get_client()

    payload = {
        "user_message": user_message,
        "tool": tool_name,
        "tool_args": tool_args,
        "tool_result": tool_result,
        "recent_messages": recent_messages,
    }

    prompt = json.dumps(payload, ensure_ascii=False, indent=2)

    resp = client.models.generate_content(
        model=MODEL_NAME,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_INSTRUCTION,
            temperature=0.3,
            max_output_tokens=400,
        ),
    )

    return (resp.text or "").strip() or "I couldn't generate a response from the available data."