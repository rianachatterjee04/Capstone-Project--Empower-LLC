import os
import requests
import time

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")
SECRET = os.getenv("INTERNAL_AI_SHARED_SECRET", "dev-internal-secret")

def tick():
    r = requests.post(
        f"{BACKEND_URL}/api/internal/ai/tick/escalations",
        headers={"X-Internal-AI-Secret": SECRET},
        timeout=10,
    )
    r.raise_for_status()
    print("tick:", r.json())

if __name__ == "__main__":
    while True:
        tick()
        time.sleep(60)
