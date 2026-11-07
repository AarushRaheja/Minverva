"""Never go past the Modal spend limit. If the spend can't be read, that counts as being over the limit."""

from __future__ import annotations

import json
import subprocess
import threading
import time
import tomllib
from collections.abc import Callable
from pathlib import Path

CONFIG = Path(__file__).resolve().parents[1] / "configs/modal.toml"


class SpendUnknown(RuntimeError):
    pass


def load_config() -> dict:
    return tomllib.loads(CONFIG.read_text())


def app_cost(rows: list[dict]) -> float:
    """Apps only. Volumes are covered by free storage on the billing summary, and don't draw on the credits."""
    return sum(float(r["cost"]) for r in rows if str(r.get("object_id", "")).startswith("ap-"))


def read_report(count_from: str) -> float:
    try:
        p = subprocess.run(["modal", "billing", "report", "--start", count_from, "--resolution", "h", "--json"],
                           capture_output=True, text=True, timeout=120)
        if p.returncode != 0:
            raise SpendUnknown(p.stderr[-300:] or p.stdout[-300:])
        return app_cost(json.loads(p.stdout))
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError) as e:
        raise SpendUnknown(f"{type(e).__name__}: {e}") from e


class SpendGuard:
    """The most that could have been spent: what billing reports, plus this session's GPU time billing may not show yet."""

    def __init__(self, cfg: dict, read: Callable[[], float] | None = None, clock: Callable[[], float] = time.time):
        self.cfg, self.clock = cfg, clock
        self.read = read or (lambda: read_report(cfg["count_from"]))
        self.lock = threading.Lock()
        self.started = clock()
        self.reported: float | None = None
        self.read_at = 0.0
        self.error: str | None = None

    def _refresh(self) -> None:
        now = self.clock()
        if self.reported is not None and now - self.read_at < self.cfg["refresh_seconds"]:
            return
        try:
            self.reported, self.read_at, self.error = self.read(), now, None
        except SpendUnknown as e:
            self.error = str(e)

    def spent(self) -> float:
        """Raises SpendUnknown if the figure is missing or too old to trust."""
        with self.lock:
            self._refresh()
            now = self.clock()
            if self.reported is None or now - self.read_at > self.cfg["max_stale_seconds"]:
                raise SpendUnknown(self.error or "billing hasn't been read recently")
            unreported = min((now - self.started) / 3600, self.cfg["reporting_lag_hours"])
            return self.reported + unreported * self.cfg["rate_usd_per_hour"]

    def blocked(self, reserve_usd: float = 0.0) -> str | None:
        """Why not to spend reserve_usd more, or None if it fits."""
        try:
            spent = self.spent()
        except SpendUnknown as e:
            return f"can't read Modal spend, so nothing more will run: {e}"
        if spent + reserve_usd >= self.cfg["cap_usd"]:
            return f"Modal limit: about ${spent:.2f} spent + ${reserve_usd:.2f} needed reaches the ${self.cfg['cap_usd']:.2f} cap"
        return None

    def status(self) -> dict:
        try:
            return {"spent_usd": round(self.spent(), 2), "cap_usd": self.cfg["cap_usd"], "reported_usd": self.reported}
        except SpendUnknown as e:
            return {"spent_usd": None, "cap_usd": self.cfg["cap_usd"], "error": str(e)}
