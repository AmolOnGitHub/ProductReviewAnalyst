from typing import Literal, TypedDict, NotRequired

ToolName = Literal["metrics_top_categories", "sentiment_summary", "rating_distribution"]

class ToolCall(TypedDict):
    tool: ToolName
    args: dict
    rationale: NotRequired[str]  # optional, for debugging