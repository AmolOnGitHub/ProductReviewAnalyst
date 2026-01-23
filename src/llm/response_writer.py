from __future__ import annotations
import json
import math
from typing import Any, Dict

from google.genai import types
from src.llm.gemini_client import get_client, MODEL_NAME

SYSTEM_INSTRUCTION = """
You are an analytics assistant helping users understand product review data.

You MUST:
- Answer ONLY using the provided tool results.
- Not invent facts or categories.
- Be concise, clear, and professional.
- If the data does not show clear or recurring issues, explicitly state that feedback is overwhelmingly positive. In that case, summarize the most common positive reasons instead of issues. 
- Do not invent problems.

Response style by tool:
- general_query: Give a direct, helpful answer to the user's question using the data.
- sentiment_summary: Summarize the key sentiments/reasons found in the reviews.
- metrics_top_categories: Briefly acknowledge the plot was updated and mention what's shown.
- rating_distribution: Briefly acknowledge the plot was updated for the category.

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

    assistant_text = (resp.text or "").strip() or "I couldn't generate a response from the available data."
    assistant_text = add_grounding(tool_name, tool_result, assistant_text)
    return assistant_text


def add_grounding(tool: str, tool_result: Dict[str, Any], response: str) -> str:
    """
    Appends evidence-based grounding statements to the response.
    """

    if not isinstance(tool_result, dict):
        return response

    def _coerce_int(value: Any) -> int | None:
        if isinstance(value, bool):
            return None
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            if not math.isfinite(value) or not value.is_integer():
                return None
            return int(value)
        return None

    def _format_count(value: Any) -> str | None:
        count = _coerce_int(value)
        if count is None:
            return None
        return f"{count:,}"

    additions: list[str] = []

    if tool == "metrics_top_categories":
        metrics = tool_result.get("metrics")
        if isinstance(metrics, list) and metrics:
            metric = tool_result.get("sorted_by")
            metric_labels = {
                "review_count": "review count",
                "avg_rating": "average rating",
                "nps": "NPS",
            }
            metric_label = metric_labels.get(metric)
            base = f"This ranking is based on {len(metrics)} categories"
            if metric_label:
                base += f" sorted by {metric_label}"
            base += "."
            additions.append(base)

            top = metrics[0] if isinstance(metrics[0], dict) else None
            count_text = _format_count(top.get("review_count") if top else None)
            if count_text:
                additions.append(f"The top category is supported by {count_text} reviews.")

    elif tool == "rating_distribution":
        dist = tool_result.get("rating_distribution")
        if isinstance(dist, dict) and dist:
            total = 0
            for value in dist.values():
                count = _coerce_int(value)
                if count is not None:
                    total += count
            if total > 0:
                category = tool_result.get("category")
                if isinstance(category, str) and category.strip():
                    additions.append(
                        f"This distribution is based on {total:,} reviews for {category}."
                    )
                else:
                    additions.append(f"This distribution is based on {total:,} reviews.")

    elif tool == "sentiment_summary":
        sent = tool_result.get("sentiment")
        if isinstance(sent, dict):
            count_text = _format_count(sent.get("review_count_analyzed"))
            if count_text:
                additions.append(f"These insights are based on {count_text} reviews.")
                reasons = sent.get("top_reasons")
                if isinstance(reasons, list) and reasons:
                    first = reasons[0]
                    if isinstance(first, (list, tuple)) and len(first) >= 2:
                        reason, count = first[0], first[1]
                        reason_count = _format_count(count)
                        if isinstance(reason, str) and reason.strip() and reason_count:
                            additions.append(
                                f'The most common theme ("{reason}") appeared in {reason_count} reviews.'
                            )

    elif tool == "general_query":
        total_reviews = _format_count(tool_result.get("total_reviews"))
        total_categories = _format_count(tool_result.get("total_categories"))
        if total_reviews and total_categories:
            additions.append(
                f"This summary covers {total_categories} categories and {total_reviews} reviews."
            )
        elif total_reviews:
            additions.append(f"This summary is based on {total_reviews} reviews.")
        elif total_categories:
            additions.append(f"This summary covers {total_categories} categories.")

    if additions:
        response = f"{response}\n\n{' '.join(additions[:2])}"

    return response
