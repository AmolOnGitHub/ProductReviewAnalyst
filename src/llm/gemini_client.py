import os
from google import genai

MODEL_NAME = "gemini-2.5-flash-lite"

def get_client():
    return genai.Client(
        api_key=os.getenv("GEMINI_API_KEY")
    )

