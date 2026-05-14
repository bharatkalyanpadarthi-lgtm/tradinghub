from __future__ import annotations

import sqlite3

from tradenest.config import Settings
from tradenest.schemas import SignalState


class SignalEngineStage:
    rubric_version = "cvd_rubric_v1"

    def __call__(
        self,
        state: SignalState,
        db: sqlite3.Connection,
        settings: Settings,
    ) -> SignalState:
        reason_codes = []
        signal_valid = True

        if state.payload.strategy != self.rubric_version:
            signal_valid = False
            reason_codes.append("unsupported_rubric")

        state.signal_valid = signal_valid
        state.signal_grade = "pass" if signal_valid else "reject"
        state.rubric_version = self.rubric_version
        state.reason_codes = reason_codes or ["deterministic_placeholder_pass"]
        return state
