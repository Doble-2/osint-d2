"""Activity Timeline & Geotemporal Inactivity (Sleep Window) Triangulation.

Analyzes UTC timestamps from Git commits, public events and posts to infer:
1. Hourly activity histogram (0-23 UTC).
2. Sleep window (consecutive 6-8 hours of minimum activity).
3. Probable timezone offset (e.g. UTC-4, UTC-5).
"""

from __future__ import annotations

from typing import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class TimezoneInference:
    probable_utc_offset: int
    confidence: float
    sleep_start_utc: int
    sleep_end_utc: int
    hourly_histogram: dict[int, int] = field(default_factory=dict)
    total_events: int = 0


class ActivityTimeline:
    """Forensic timeline and geotemporal triangulator."""

    @staticmethod
    def infer_timezone_from_timestamps(
        timestamps: Sequence[datetime | str],
        sleep_window_hours: int = 7,
    ) -> TimezoneInference:
        """Infers probable UTC offset based on the least active consecutive hours.

        Standard biological sleep window assumed: ~01:00 to 08:00 local time.
        """
        histogram = {h: 0 for h in range(24)}
        valid_events = 0

        for ts in timestamps:
            dt: datetime | None = None
            if isinstance(ts, str):
                try:
                    # ISO format parsing (e.g. 2026-10-01T15:30:00Z)
                    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                except ValueError:
                    continue
            elif isinstance(ts, datetime):
                dt = ts

            if dt:
                # Convert to UTC
                dt_utc = dt.astimezone(timezone.utc)
                histogram[dt_utc.hour] += 1
                valid_events += 1

        if valid_events < 5:
            # Not enough data points
            return TimezoneInference(
                probable_utc_offset=0,
                confidence=0.1,
                sleep_start_utc=0,
                sleep_end_utc=sleep_window_hours,
                hourly_histogram=histogram,
                total_events=valid_events,
            )

        # Sliding window circular (24h) to find minimum activity block
        min_activity = float("inf")
        best_start = 0

        for start_hour in range(24):
            current_window_activity = sum(
                histogram[(start_hour + i) % 24] for i in range(sleep_window_hours)
            )
            if current_window_activity < min_activity:
                min_activity = current_window_activity
                best_start = start_hour

        sleep_start_utc = best_start
        sleep_end_utc = (best_start + sleep_window_hours) % 24

        # Find the center of gravity of inactivity.
        # Zero activity window starts at best_start and lasts sleep_window_hours.
        # Biological center of sleep is typically ~04:00 AM local time.
        sleep_midpoint_utc = (best_start + (sleep_window_hours / 2.0)) % 24

        # Local 04:00 = UTC + offset  => offset = 4.0 - sleep_midpoint_utc
        # Note: if best_start is 5 (05:00 UTC) and sleep 7h -> midpoint is 8.5 UTC -> 4.0 - 8.5 = -4.5 -> -4 / -5
        raw_offset = 4.0 - sleep_midpoint_utc
        if raw_offset < -12:
            raw_offset += 24
        elif raw_offset > 14:
            raw_offset -= 24

        probable_offset = int(round(raw_offset))

        # Confidence calculation based on contrast
        total = float(valid_events)
        active_ratio = (total - min_activity) / total
        confidence = min(0.95, round(active_ratio * (1.0 - (min_activity / total)), 2))

        return TimezoneInference(
            probable_utc_offset=probable_offset,
            confidence=max(0.2, confidence),
            sleep_start_utc=sleep_start_utc,
            sleep_end_utc=sleep_end_utc,
            hourly_histogram=histogram,
            total_events=valid_events,
        )
