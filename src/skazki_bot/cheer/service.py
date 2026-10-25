"""Luna's warm-words service: composes messages, remembers what was sent, picks who is due.

No Telegram here: sending lives in `scheduler.py` (proactive) and `bot/handlers/cheer.py`
(on request). That keeps this module easy to test against SQLite alone.
"""

from __future__ import annotations

import random
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from skazki_bot.cheer.compose import CheerMessage, compose
from skazki_bot.cheer.schedule import FREQUENCIES, is_due
from skazki_bot.cheer.skill import CheerSkill, load_cheer_skill
from skazki_bot.config import Settings
from skazki_bot.db import repo
from skazki_bot.db.base import SessionFactory
from skazki_bot.knowledge.cheer_kb import CheerKB, load_cheer_kb
from skazki_bot.logging import get_logger

log = get_logger(__name__)


class CheerService:
    def __init__(
        self,
        *,
        sf: SessionFactory,
        settings: Settings,
        kb: CheerKB | None = None,
        skill: CheerSkill | None = None,
        rng: random.Random | None = None,
    ) -> None:
        self._sf = sf
        self._settings = settings
        self.kb = kb or load_cheer_kb()
        self.skill = skill or load_cheer_skill()
        self._rng = rng or random.Random()

    # --- Composing --------------------------------------------------------------------------------
    def _local_hour(self, now: datetime | None) -> int:
        tz = ZoneInfo(self._settings.timezone)
        return (now or datetime.now(UTC)).astimezone(tz).hour

    async def prepare(
        self, user_id: int, mood: str | None = None, *, now: datetime | None = None
    ) -> CheerMessage:
        """Compose a message for this user: time of day, mood, child's name and history aware."""
        async with self._sf() as session:
            child_name, recent = await repo.cheer_context(session, user_id)
        return compose(
            self.kb,
            local_hour=self._local_hour(now),
            mood=mood,
            child_name=child_name,
            recent=recent,
            rng=self._rng,
        )

    async def record_sent(self, user_id: int, item_id: str, *, now: datetime | None = None) -> None:
        """Remember the item (no repeats for a while) and the moment (delays the next message)."""
        async with self._sf.begin() as session:
            await repo.push_cheer_sent(
                session,
                user_id,
                item_id,
                limit=self.skill.meta.recent_memory,
                now=now or datetime.now(UTC),
            )

    # --- Preferences ------------------------------------------------------------------------------
    async def set_frequency(self, user_id: int, freq: str) -> bool:
        if freq not in FREQUENCIES:
            return False
        async with self._sf.begin() as session:
            await repo.set_cheer_freq(session, user_id, freq)
        return True

    async def disable(self, user_id: int) -> None:
        await self.set_frequency(user_id, "off")

    # --- Proactive schedule -------------------------------------------------------------------------
    async def claim_due(self, now: datetime | None = None) -> list[int]:
        """User ids whose turn it is. Each is *claimed* atomically in the database, so even several
        bot replicas never send the same user two messages."""
        cfg = self._settings
        if not cfg.cheer_enabled:
            return []
        now = now or datetime.now(UTC)
        tz = ZoneInfo(cfg.timezone)
        gaps = self.skill.gaps()
        async with self._sf() as session:
            candidates = await repo.list_cheer_candidates(session)

        claimed: list[int] = []
        for cand in candidates:
            if len(claimed) >= cfg.cheer_batch_size:
                break
            due = is_due(
                now=now,
                tz=tz,
                user_id=cand.user_id,
                freq=cand.freq,
                last_at=cand.last_at,
                window_start=cfg.cheer_window_start,
                window_end=cfg.cheer_window_end,
                gaps=gaps,
            )
            if not due:
                continue
            async with self._sf.begin() as session:
                won = await repo.claim_cheer_slot(
                    session, cand.user_id, now=now, cutoff=now - gaps[cand.freq]
                )
            if won:
                claimed.append(cand.user_id)
        return claimed
