from ollama import chat
import os
from dotenv import load_dotenv
from app.agent.models import schema
from app.prompts.sys_prompt_test import SYSTEM_PROMPT

load_dotenv()
PRIMARY_MODEL = os.getenv("PRIMARY_MODEL")
SECONDARY_MODEL = os.getenv("SECONDARY_MODEL")


def call_qwen(prompt,thinking = True):
    response = chat(
        model = PRIMARY_MODEL if not thinking else SECONDARY_MODEL,
        messages=[
            {
                "role":"system",
                "content":SYSTEM_PROMPT
            },
            {
                "role":"user",
                "content":prompt
            }
        ],   
        format=schema,
    )
    
    return response.message.content