from ollama import chat
import os
from dotenv import load_dotenv
from app.agent.models import schema
from app.prompts.skill_loader import build_system_prompt

load_dotenv()
PRIMARY_MODEL = os.getenv("PRIMARY_MODEL")
SECONDARY_MODEL = os.getenv("SECONDARY_MODEL")


def call_qwen(prompt, thinking=True):
    system_prompt = build_system_prompt(prompt)

    response = chat(
        model=PRIMARY_MODEL if not thinking else SECONDARY_MODEL,
        messages=[
            {
                "role": "system",
                "content": system_prompt
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        format=schema,
        options={
            "temperature": 0.2,
            "seed": 0,
        },
    )

    return response.message.content