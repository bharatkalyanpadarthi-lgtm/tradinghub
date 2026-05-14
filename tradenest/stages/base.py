from __future__ import annotations

import sqlite3
from typing import Protocol

from tradenest.config import Settings
from tradenest.schemas import SignalState


class Stage(Protocol):
    def __call__(
        self,
        state: SignalState,
        db: sqlite3.Connection,
        settings: Settings,
    ) -> SignalState:
        ...
