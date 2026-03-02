from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx


class TranscriptionProvider:
    def __init__(self, *, api_key: str, base_url: str = "https://api.groq.com/openai/v1", model: str = "whisper-large-v3-turbo") -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model

    async def transcribe(self, audio_path: str | Path, *, language: str = "pt") -> str:
        path = Path(audio_path)
        if not path.exists():
            raise FileNotFoundError(str(path))

        headers = {"authorization": f"Bearer {self.api_key}"}
        files = {"file": (path.name, path.read_bytes(), "audio/mpeg")}
        data: dict[str, Any] = {"model": self.model, "language": language}

        async with httpx.AsyncClient(timeout=90) as client:
            response = await client.post(f"{self.base_url}/audio/transcriptions", headers=headers, files=files, data=data)
            response.raise_for_status()
            payload = response.json()
        return str(payload.get("text", "")).strip()
