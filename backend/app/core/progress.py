from __future__ import annotations

from datetime import datetime
from time import perf_counter


TOTAL_STEPS = 18
_started_at: float | None = None
_last_step_at: float | None = None


def format_seconds(seconds: float) -> str:
    if seconds < 1:
        return f"{seconds * 1000:.0f}ms"
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes = int(seconds // 60)
    remainder = seconds - minutes * 60
    return f"{minutes}m {remainder:.1f}s"


def log_step(step: int, message: str) -> None:
    global _started_at, _last_step_at

    now = perf_counter()
    if _started_at is None or step <= 1:
        _started_at = now
        _last_step_at = now

    previous = _last_step_at if _last_step_at is not None else now
    step_elapsed = now - previous
    total_elapsed = now - (_started_at if _started_at is not None else now)
    _last_step_at = now

    timestamp = datetime.now().strftime("%H:%M:%S")
    print(
        f"[{step:02d}/{TOTAL_STEPS}] {timestamp} "
        f"(+{format_seconds(step_elapsed)}, total {format_seconds(total_elapsed)}) {message}",
        flush=True,
    )
