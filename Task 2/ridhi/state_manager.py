"""
Session state manager — Redis with in-memory fallback.

Implements checkpoint persistence, 24-hour session window tracking,
and re-engagement flow triggers.
"""

from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from ridhi.checkpoints import Checkpoint, OnboardingData

# TTL constants (seconds) — see docs/ARCHITECTURE.md
ONBOARDING_TTL_SECONDS = 90 * 24 * 3600  # 90 days
SESSION_META_TTL_SECONDS = 48 * 3600  # 48 hours
SESSION_WINDOW_HOURS = 24


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


@dataclass
class CPState:
    cp_id: str
    wa_id: str
    language: str = "hi"
    last_checkpoint: Checkpoint = Checkpoint.NAME_COLLECTION
    completed_checkpoints: list[str] = field(default_factory=list)
    data: OnboardingData = field(default_factory=OnboardingData)
    last_user_message_at: str | None = None
    last_bot_message_at: str | None = None
    session_window_expires_at: str | None = None
    re_engagement_count: int = 0
    version: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "cp_id": self.cp_id,
            "wa_id": self.wa_id,
            "language": self.language,
            "last_checkpoint": self.last_checkpoint.value,
            "completed_checkpoints": list(self.completed_checkpoints),
            "data": self.data.to_dict(),
            "last_user_message_at": self.last_user_message_at,
            "last_bot_message_at": self.last_bot_message_at,
            "session_window_expires_at": self.session_window_expires_at,
            "re_engagement_count": self.re_engagement_count,
            "version": self.version,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> CPState:
        return cls(
            cp_id=raw["cp_id"],
            wa_id=raw["wa_id"],
            language=raw.get("language", "hi"),
            last_checkpoint=Checkpoint(raw.get("last_checkpoint", Checkpoint.NAME_COLLECTION.value)),
            completed_checkpoints=list(raw.get("completed_checkpoints") or []),
            data=OnboardingData.from_dict(raw.get("data")),
            last_user_message_at=raw.get("last_user_message_at"),
            last_bot_message_at=raw.get("last_bot_message_at"),
            session_window_expires_at=raw.get("session_window_expires_at"),
            re_engagement_count=int(raw.get("re_engagement_count") or 0),
            version=int(raw.get("version") or 1),
        )


class StateBackend(ABC):
    @abstractmethod
    def get(self, key: str) -> dict[str, Any] | None: ...

    @abstractmethod
    def set(self, key: str, value: dict[str, Any], ttl_seconds: int) -> None: ...

    @abstractmethod
    def setnx(self, key: str, value: str, ttl_seconds: int) -> bool: ...


class InMemoryBackend(StateBackend):
    def __init__(self) -> None:
        self._store: dict[str, tuple[dict[str, Any], float | None]] = {}
        self._locks: dict[str, str] = {}

    def get(self, key: str) -> dict[str, Any] | None:
        item = self._store.get(key)
        if not item:
            return None
        value, expires_at = item
        if expires_at is not None and _utcnow().timestamp() > expires_at:
            del self._store[key]
            return None
        return json.loads(json.dumps(value))

    def set(self, key: str, value: dict[str, Any], ttl_seconds: int) -> None:
        expires = _utcnow().timestamp() + ttl_seconds if ttl_seconds > 0 else None
        self._store[key] = (value, expires)

    def setnx(self, key: str, value: str, ttl_seconds: int) -> bool:
        if key in self._locks:
            return False
        self._locks[key] = value
        return True


class RedisBackend(StateBackend):
    def __init__(self, url: str) -> None:
        import redis

        self._client = redis.from_url(url, decode_responses=True)

    def get(self, key: str) -> dict[str, Any] | None:
        raw = self._client.get(key)
        if not raw:
            return None
        return json.loads(raw)

    def set(self, key: str, value: dict[str, Any], ttl_seconds: int) -> None:
        self._client.setex(key, ttl_seconds, json.dumps(value))

    def setnx(self, key: str, value: str, ttl_seconds: int) -> bool:
        return bool(self._client.set(key, value, nx=True, ex=ttl_seconds))


class SessionStateManager:
    """
    Persists CP onboarding state and tracks WhatsApp 24-hour session windows.
    """

    def __init__(self, backend: StateBackend | None = None) -> None:
        if backend is not None:
            self._backend = backend
        else:
            redis_url = os.getenv("REDIS_URL")
            if redis_url:
                try:
                    self._backend = RedisBackend(redis_url)
                except Exception:
                    self._backend = InMemoryBackend()
            else:
                self._backend = InMemoryBackend()

    @staticmethod
    def onboarding_key(wa_id: str) -> str:
        return f"ridhi:cp:{wa_id}:onboarding"

    @staticmethod
    def session_key(wa_id: str) -> str:
        return f"ridhi:cp:{wa_id}:session"

    @staticmethod
    def idempotency_key(wa_id: str, wamid: str) -> str:
        return f"ridhi:cp:{wa_id}:msg:{wamid}"

    def load_state(self, wa_id: str) -> CPState | None:
        raw = self._backend.get(self.onboarding_key(wa_id))
        if not raw:
            return None
        return CPState.from_dict(raw)

    def save_state(self, state: CPState) -> None:
        state.version += 1
        self._backend.set(
            self.onboarding_key(state.wa_id),
            state.to_dict(),
            ONBOARDING_TTL_SECONDS,
        )
        self._update_session_meta(state)

    def get_or_create(self, wa_id: str, language: str = "hi") -> CPState:
        existing = self.load_state(wa_id)
        if existing:
            return existing
        state = CPState(
            cp_id=f"cp_{uuid4().hex[:8]}",
            wa_id=wa_id,
            language=language,
            last_checkpoint=Checkpoint.NAME_COLLECTION,
        )
        self.save_state(state)
        return state

    def save_checkpoint(
        self,
        wa_id: str,
        checkpoint: Checkpoint,
        data: OnboardingData,
    ) -> CPState:
        state = self.load_state(wa_id) or self.get_or_create(wa_id)
        cp_name = checkpoint.value
        if cp_name not in state.completed_checkpoints:
            state.completed_checkpoints.append(cp_name)
        state.last_checkpoint = checkpoint
        state.data = data
        self.save_state(state)
        return state

    def record_user_message(self, wa_id: str, at: datetime | None = None) -> CPState:
        """Update last user message time and reset 24h session window."""
        state = self.get_or_create(wa_id)
        now = at or _utcnow()
        state.last_user_message_at = _iso(now)
        state.session_window_expires_at = _iso(
            now + timedelta(hours=SESSION_WINDOW_HOURS)
        )
        self.save_state(state)
        return state

    def record_bot_message(self, wa_id: str) -> CPState:
        state = self.get_or_create(wa_id)
        state.last_bot_message_at = _iso(_utcnow())
        self.save_state(state)
        return state

    def is_session_expired(self, state: CPState, at: datetime | None = None) -> bool:
        expires = _parse_iso(state.session_window_expires_at)
        if expires is None:
            return False
        now = at or _utcnow()
        return now > expires

    def mark_re_engagement(self, wa_id: str) -> CPState:
        state = self.get_or_create(wa_id)
        state.re_engagement_count += 1
        self.save_state(state)
        return state

    def claim_message_id(self, wa_id: str, wamid: str) -> bool:
        """Returns True if this is the first time we see this wamid."""
        return self._backend.setnx(
            self.idempotency_key(wa_id, wamid),
            "1",
            7 * 24 * 3600,
        )

    def _update_session_meta(self, state: CPState) -> None:
        expired = self.is_session_expired(state)
        meta = {
            "expires_at": state.session_window_expires_at or "",
            "is_expired": "1" if expired else "0",
            "re_engagement_count": str(state.re_engagement_count),
        }
        self._backend.set(self.session_key(state.wa_id), meta, SESSION_META_TTL_SECONDS)
