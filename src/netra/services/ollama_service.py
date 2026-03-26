from typing import Optional

import requests


class OllamaService:
    def __init__(self, host: str, port: int, model: str) -> None:
        self.host = host
        self.port = port
        self.model = model
        self.generate_url = f"http://{host}:{port}/api/generate"
        self.tags_url = f"http://{host}:{port}/api/tags"

    def is_available(self) -> bool:
        try:
            # Check if the process is even listening on the port first
            response = requests.get(self.tags_url, timeout=2)
            return response.status_code == 200
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
            return False
        except Exception:
            return False

    def generate(self, prompt: str, system: Optional[str] = None, timeout: int = 60) -> str:
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
        }
        if system:
            payload["system"] = system
        response = requests.post(self.generate_url, json=payload, timeout=timeout)
        response.raise_for_status()
        return response.json().get("response", "").strip()
