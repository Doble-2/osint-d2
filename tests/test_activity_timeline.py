from datetime import datetime, timezone
from adapters.activity_timeline import ActivityTimeline


def test_activity_timeline_sleep_window_utc_minus_4():
    # Usuario que comitea activamente entre 13:00 y 04:00 UTC (09:00 a 00:00 en UTC-4)
    # y duerme/no registra actividad entre 05:00 y 12:00 UTC (01:00 a 08:00 en UTC-4)
    timestamps = []
    for day in range(1, 10):
        for h in [13, 15, 17, 19, 21, 23, 1, 3]:
            timestamps.append(datetime(2026, 10, day, h, 15, tzinfo=timezone.utc))

    res = ActivityTimeline.infer_timezone_from_timestamps(timestamps, sleep_window_hours=7)

    # Ventana de inactividad detectada debe empezar en 04:00 o 05:00 UTC
    assert 4 <= res.sleep_start_utc <= 6
    # Zona horaria inferida debe ser UTC-4 o UTC-5
    assert res.probable_utc_offset in (-4, -5)
    assert res.confidence > 0.8
    assert res.total_events == len(timestamps)


def test_activity_timeline_insufficient_data():
    timestamps = [datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)]
    res = ActivityTimeline.infer_timezone_from_timestamps(timestamps)
    assert res.confidence <= 0.2
    assert res.total_events == 1
