"""Background loop that delivers Luna's warm messages to users who opted in."""

from __future__ import annotations

import asyncio
from datetime import datetime

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramForbiddenError, TelegramRetryAfter

from skazki_bot.bot import keyboards as kb
from skazki_bot.cheer.service import CheerService
from skazki_bot.logging import get_logger

log = get_logger(__name__)

SEND_DELAY_S = 0.07  # ~14 messages/s: well under Telegram's broadcast limits


class CheerScheduler:
    def __init__(
        self, service: CheerService, bot: Bot, *, tick_s: float, send_delay_s: float = SEND_DELAY_S
    ) -> None:
        self._service = service
        self._bot = bot
        self._tick_s = tick_s
        self._delay = send_delay_s

    async def run_once(self, now: datetime | None = None) -> int:
        """One pass: claim everyone who is due and send. Returns the number of messages sent."""
        sent = 0
        for user_id in await self._service.claim_due(now):
            if await self._send(user_id, now):
                sent += 1
            await asyncio.sleep(self._delay)
        return sent

    async def run_forever(self) -> None:
        log.info("cheer_scheduler_started", tick_s=self._tick_s)
        while True:
            try:
                await self.run_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                log.error("cheer_tick_failed", exc_info=True)
            await asyncio.sleep(self._tick_s)

    async def _send(self, user_id: int, now: datetime | None) -> bool:
        message = await self._service.prepare(user_id, now=now)
        for attempt in (1, 2):
            try:
                await self._bot.send_message(
                    user_id, message.html, reply_markup=kb.cheer_message_kb()
                )
            except TelegramForbiddenError:
                await self._service.disable(user_id)  # blocked the bot: stop for good
                log.info("cheer_user_blocked")
                return False
            except TelegramRetryAfter as exc:
                if attempt == 2:
                    log.warning("cheer_rate_limited")
                    return False
                await asyncio.sleep(float(exc.retry_after))
            except TelegramAPIError:
                log.warning("cheer_send_failed", exc_info=True)
                return False
            else:
                await self._service.record_sent(user_id, message.item_id, now=now)
                log.info("cheer_sent", kind=message.kind, item=message.item_id)
                return True
        return False
