import json
from typing import Any

from openai import AsyncOpenAI

from app.core.config import Settings


class LLMService:
    def __init__(self, settings: Settings, client: AsyncOpenAI | None = None) -> None:
        self.settings = settings
        self.client = client

    def _require_key(self) -> None:
        if not self.settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is not configured")

    def _client(self) -> AsyncOpenAI:
        self._require_key()
        if self.client is None:
            self.client = AsyncOpenAI(api_key=self.settings.openai_api_key)
        return self.client

    async def embed(self, texts: list[str]) -> list[list[float]]:
        response = await self._client().embeddings.create(
            model=self.settings.openai_embedding_model,
            input=texts,
            dimensions=self.settings.embedding_dimensions,
        )
        return [item.embedding for item in response.data]

    async def extract_booking_fields(self, message: str, history: list[dict[str, str]]) -> dict[str, Any]:
        client = self._client()
        history_text = "\n".join(f"{item['role']}: {item['content']}" for item in history[-8:])
        response = await client.chat.completions.create(
            model=self.settings.openai_chat_model,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Classify whether the user wants to book an interview. Return ONLY JSON with keys "
                        "intent (booking or question), full_name, email, interview_date (YYYY-MM-DD or null), "
                        "interview_time (24-hour HH:MM or null), confirmation (true/false/null), and cancel "
                        "(true/false). Extract only explicit details. confirmation is true only for a clear "
                        "yes/confirm after a booking summary, false only for a clear no, otherwise null. "
                        "Treat the current user message as the source for newly supplied details."
                    ),
                },
                {"role": "user", "content": f"Recent conversation:\n{history_text}\n\nNew message:\n{message}"},
            ],
            temperature=0,
        )
        content = response.choices[0].message.content
        if not content:
            raise RuntimeError("The language model returned an empty booking-intent response")
        try:
            payload = json.loads(content)
        except json.JSONDecodeError as exc:
            raise RuntimeError("The language model returned invalid booking-intent JSON") from exc
        if not isinstance(payload, dict):
            raise RuntimeError("The language model returned an invalid booking-intent shape")
        return payload

    async def answer(self, question: str, history: list[dict[str, str]], context: str) -> str:
        client = self._client()
        messages: list[dict[str, str]] = [
            {
                "role": "system",
                "content": (
                    "Answer the user using the supplied document context and relevant conversation history. "
                    "Do not invent facts or citations. If the context does not contain the answer, say so "
                    "clearly. Keep the answer concise. Context:\n" + (context or "(No matching document passages.)")
                ),
            }
        ]
        messages.extend({"role": item["role"], "content": item["content"]} for item in history[-12:])
        messages.append({"role": "user", "content": question})
        response = await client.chat.completions.create(
            model=self.settings.openai_chat_model,
            messages=messages,
            temperature=0.2,
        )
        answer = response.choices[0].message.content
        if not answer:
            raise RuntimeError("The language model returned an empty answer")
        return answer.strip()
