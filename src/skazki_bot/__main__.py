from __future__ import annotations

import asyncio
import contextlib

from skazki_bot.app import run
from skazki_bot.config import get_settings
from skazki_bot.logging import setup_logging


def main() -> None:
    settings = get_settings()
    setup_logging(settings.log_level, json_logs=settings.log_json)
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(run(settings))


if __name__ == "__main__":
    main()
