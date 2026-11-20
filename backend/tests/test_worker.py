"""모델별 worker pool lifecycle 회귀."""

from __future__ import annotations

import threading
from pathlib import Path
from unittest.mock import Mock
from zipfile import ZipFile

import pytest

from app import config
from app.inference.models_dir import activate_lane_weights, lane_weights_path
from app.inference.worker import _model_worker_main


def _start_and_stop_model_worker(name, device="cpu"):
    stop = threading.Event()
    stop.set()
    _model_worker_main(name, None, None, stop, device, 1, 0.0, 320)


@pytest.mark.parametrize("download_succeeds", [True, False])
def test_worker_retries_interrupted_preset_once(monkeypatch, tmp_path, download_succeeds):
    monkeypatch.setattr(config, "YOLO_WEIGHTS_DIR", tmp_path)
    monkeypatch.setattr(config, "WEIGHTS_DIR", tmp_path / "uploads")
    weights = tmp_path / config.YOLO_DEFAULT_MODEL
    weights.write_bytes(b"PK\x03\x04partial")
    cached_at_load = []
    model = Mock()

    def load(path):
        assert Path(path) == weights
        cached_at_load.append(weights.exists())
        if weights.exists():
            raise RuntimeError("PytorchStreamReader failed finding central directory")
        if not download_succeeds:
            weights.write_bytes(b"partial again")
            raise ConnectionError("download interrupted")
        weights.write_bytes(b"download complete")
        return model

    monkeypatch.setattr("ultralytics.YOLO", load)
    _start_and_stop_model_worker("anchor")

    assert cached_at_load == [True, False]
    assert model.to.call_count == int(download_succeeds)


def test_worker_preserves_complete_cache_after_unrelated_failure(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "YOLO_WEIGHTS_DIR", tmp_path)
    monkeypatch.setattr(config, "WEIGHTS_DIR", tmp_path / "uploads")
    weights = tmp_path / config.YOLO_DEFAULT_MODEL
    with ZipFile(weights, "w") as checkpoint:
        checkpoint.writestr("model", "data")
    load = Mock(side_effect=RuntimeError("CPU allocator out of memory"))
    monkeypatch.setattr("ultralytics.YOLO", load)

    _start_and_stop_model_worker("anchor")

    load.assert_called_once_with(str(weights))
    assert weights.is_file()


def test_worker_preserves_uploaded_weights_on_load_failure(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "WEIGHTS_DIR", tmp_path)
    upload = tmp_path / "candidate.pt"
    upload.write_bytes(b"custom weights")
    activate_lane_weights(
        upload, lane="target", original_name="yolo26x.pt", size_bytes=14,
        classes=[{"id": 0, "name": "box"}],
    )
    load = Mock(side_effect=EOFError("incomplete file"))
    monkeypatch.setattr("ultralytics.YOLO", load)

    _start_and_stop_model_worker("target")

    load.assert_called_once_with(str(lane_weights_path("target")))
    assert lane_weights_path("target").read_bytes() == b"custom weights"


def test_worker_logs_failed_cpu_reload_after_cuda_oom(monkeypatch, tmp_path, caplog):
    monkeypatch.setattr(config, "YOLO_WEIGHTS_DIR", tmp_path)
    monkeypatch.setattr(config, "WEIGHTS_DIR", tmp_path / "uploads")
    name = "anchor"
    model = Mock()
    model.to.side_effect = RuntimeError("CUDA out of memory")
    cpu_error = OSError("CPU reload failed")
    load = Mock(side_effect=[model, cpu_error])
    monkeypatch.setattr("ultralytics.YOLO", load)
    monkeypatch.setattr("torch.cuda.empty_cache", Mock())

    _start_and_stop_model_worker(name, "cuda:0")

    model.to.assert_called_once_with("cuda:0")
    assert load.call_count == 2
    assert any(
        record.getMessage() == f"Model load failed: {name}" and record.exc_info[1] is cpu_error
        for record in caplog.records
    )
