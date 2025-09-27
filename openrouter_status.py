import requests
import json
import os
from dotenv import load_dotenv
load_dotenv()

response = requests.get(
  url="https://openrouter.ai/api/v1/key",
  headers={
    "Authorization": f"Bearer {os.getenv('OPENROUTER_API_KEY')}"
  }
)
print(json.dumps(response.json(), indent=2))
