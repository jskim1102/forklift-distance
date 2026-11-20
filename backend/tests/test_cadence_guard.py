from unittest.mock import Mock

import app.streaming.manager as manager_mod
from app.inference import InferenceResult


def test_autotune_logs_drop_totals_and_latest_cadence_every_minute(monkeypatch, caplog):
    cap = Mock(is_running=True, source_fps=30.0)
    m = manager_mod.StreamManager()
    m._captures["cam"] = cap
    m._per_source_models["cam"] = ["anchor"]
    for i in range(m._telemetry.min_samples):
        m._telemetry.observe(InferenceResult("cam", float(i), infer_ms=20.0, idle_ms=20.0))
    stats = {"dropped": 0}
    monkeypatch.setattr(m._worker, "get_queue_stats", lambda: stats)
    monkeypatch.setattr(manager_mod.time, "monotonic", lambda: now)
    caplog.set_level("DEBUG", logger=manager_mod.logger.name)

    # The worker counter resets mid-window. Earlier drops still count in the report.
    for now, count, warnings, level in [
        (0, 2, [2], "INFO"),
        (1, 4, [], "DEBUG"),
        (2, 0, [], "DEBUG"),
        (59.9, 3, [], "DEBUG"),
        (60, 3, [5], "INFO"),
        (120, 3, [], "INFO"),
    ]:
        caplog.clear()
        stats["dropped"] = count
        cap.source_fps = 15.0 if now >= 60 else 30.0
        assert m._run_autotune() is True
        assert m._last_drop_count == count
        assert [r.args[0] for r in caplog.records if r.levelname == "WARNING"] == warnings
        cadence = [r for r in caplog.records if r.message.startswith("cadence autotune:")]
        assert [r.levelname for r in cadence] == [level]
        assert f"demand={cap.source_fps:.1f}/s" in cadence[0].message
