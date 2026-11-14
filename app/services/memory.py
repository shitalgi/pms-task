import json

from redis.asyncio import Redis

from app.core.config import Settings


class RedisChatMemory:
    def __init__(self, redis: Redis, settings: Settings) -> None:
        self.redis = redis
        self.settings = settings

    @staticmethod
    def _key(session_id: str) -> str:
        return f"chat:{session_id}"

    @staticmethod
    def _booking_key(session_id: str) -> str:
        return f"booking:{session_id}"

    async def get_history(self, session_id: str) -> list[dict[str, str]]:
        raw = await self.redis.get(self._key(session_id))
        if raw is None:
            return []
        try:
            history = json.loads(raw)
        except (json.JSONDecodeError, TypeError) as exc:
            raise RuntimeError("Stored chat history is invalid JSON") from exc
        if not isinstance(history, list):
            raise RuntimeError("Stored chat history has an invalid shape")
        return history

    async def append_turn(self, session_id: str, user_message: str, assistant_message: str) -> None:
        history = await self.get_history(session_id)
        history.extend(
            [
                {"role": "user", "content": user_message},
                {"role": "assistant", "content": assistant_message},
            ]
        )
        history = history[-self.settings.chat_history_turns * 2 :]
        await self.redis.set(
            self._key(session_id),
            json.dumps(history),
            ex=self.settings.chat_memory_ttl_seconds,
        )

    async def get_booking_draft(self, session_id: str) -> dict[str, str] | None:
        raw = await self.redis.get(self._booking_key(session_id))
        if raw is None:
            return None
        try:
            draft = json.loads(raw)
        except (json.JSONDecodeError, TypeError) as exc:
            raise RuntimeError("Stored interview booking draft is invalid JSON") from exc
        if not isinstance(draft, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in draft.items()):
            raise RuntimeError("Stored interview booking draft has an invalid shape")
        return draft

    async def save_booking_draft(self, session_id: str, draft: dict[str, str]) -> None:
        await self.redis.set(
            self._booking_key(session_id),
            json.dumps(draft),
            ex=self.settings.chat_memory_ttl_seconds,
        )

    async def clear_booking_draft(self, session_id: str) -> None:
        await self.redis.delete(self._booking_key(session_id))
