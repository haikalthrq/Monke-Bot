#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import logging

from monkebot.core.app import run


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)


if __name__ == "__main__":
    asyncio.run(run())
