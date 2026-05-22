import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("OPENROUTER_API_KEY")
endpoint = "https://openrouter.ai/api/v1"
model = "openai/gpt-4.1"

client = OpenAI(
    base_url=endpoint,
    api_key=api_key,
)

response = client.chat.completions.create(
    messages=[
        {
            "role": "system",
            "content": "You are a helpful assistant.",
        },
        {
            "role": "user",
            "content": "Tell me about the 2025-26 Western USA snowpack"
        }
    ],
    model=model
)

print(response.choices[0].message.content)