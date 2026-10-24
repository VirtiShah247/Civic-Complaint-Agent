import time
import os
from dotenv import load_dotenv
load_dotenv()
from google import genai
from google.genai import types

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

# Test 1: default config
t0 = time.time()
try:
    res = client.models.generate_content(
        model="gemini-3.8-flash",
        contents="Say hi in 1 word",
    )
    print("Default config time:", round(time.time() - t0, 2), "s. Response:", res.text.strip())
except Exception as e:
    print("Default error:", e)

# Test 2: with max_output_tokens
t0 = time.time()
try:
    res = client.models.generate_content(
        model="gemini-3.8-flash",
        contents="Say hi in 1 word",
        config=types.GenerateContentConfig(
            max_output_tokens=50,
            temperature=0.0
        )
    )
    print("Low max_output_tokens time:", round(time.time() - t0, 2), "s. Response:", res.text.strip())
except Exception as e:
    print("Low tokens error:", e)

# Test 3: check if thinking_config exists
t0 = time.time()
try:
    res = client.models.generate_content(
        model="gemini-3.8-flash",
        contents="Say hi in 1 word",
        config=types.GenerateContentConfig(
            max_output_tokens=50,
            thinking_config=types.ThinkingConfig(thinking_budget=0)
        )
    )
    print("Thinking budget 0 time:", round(time.time() - t0, 2), "s. Response:", res.text.strip())
except Exception as e:
    print("Thinking config test:", e)
