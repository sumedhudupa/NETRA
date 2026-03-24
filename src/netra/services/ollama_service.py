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
            response = requests.get(self.tags_url, timeout=5)
            response.raise_for_status()
            return True
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
