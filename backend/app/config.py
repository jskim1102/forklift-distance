import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# backend/.env 를 로드
_env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_env_path)

# 빈 문자열(set-but-empty)도 미설정으로 취급해 안전기본 폴백 (codex #3).
#   os.getenv(k, default) 는 k 가 "" 면 ""(빈값)을 그대로 돌려준다 → CORS_ORIGINS="" → [""]
#   (기본 * 아님 → CORS 차단), MAX_IPCAMS="" → int("") → ValueError(import 크래시).
#   `or` 로 빈값=거짓 → 기본값으로 폴백한다.
CORS_ORIGINS: str = os.getenv("CORS_ORIGINS") or "*"

_raw_max_ipcams = int(os.getenv("MAX_IPCAMS") or "16")
MAX_IPCAMS: int = max(1, min(64, _raw_max_ipcams))

# mediamtx API 주소 — 하드코딩 fallback 을 두지 않는다(빈 문자열 = 미설정).
# Docker compose 가 environment 블록으로 `http://mediamtx:9997` 를 주입하고,
# 로컬 실행 시에는 backend/.env 에 설정한다. 실제로 호출하는 app.mediamtx 가
# 미설정이면 명시 에러를 낸다(import 시점엔 raise 안 함 — 순수 import/테스트 허용).
MEDIAMTX_API: str = os.getenv("MEDIAMTX_API", "")

# mediamtx 인증(#100) — backend user 로 API 호출 시 Basic auth. 비번 비우면 무인증(로컬/테스트 하위호환).
MEDIAMTX_BACKEND_USER: str = os.getenv("MEDIAMTX_BACKEND_USER", "backend")
MEDIAMTX_BACKEND_PASS: str = os.getenv("MEDIAMTX_BACKEND_PASS", "")

# WebRTC 외부접속 광고 호스트(공인 IP). mediamtx.yml 의 webrtcAdditionalHosts 로
# 주입된다. 미설정이면 mediamtx 가 컨테이너 내부 주소만 광고 → 외부에서 영상 안 나옴.
MEDIAMTX_WEBRTC_HOST: str = os.getenv("MEDIAMTX_WEBRTC_HOST", "")

# ── detection (YOLO 추론 — rtsp-detection 모듈과 동일 런타임 계약) ──
PRESET_MODELS: tuple[str, ...] = (
    "yolo26n.pt",
    "yolo26s.pt",
    "yolo26m.pt",
    "yolo26l.pt",
    "yolo26x.pt",
)
_raw_yolo_model = os.getenv("YOLO_DEFAULT_MODEL", "")
YOLO_DEFAULT_MODEL = _raw_yolo_model if _raw_yolo_model in PRESET_MODELS else "yolo26x.pt"
YOLO_WEIGHTS_DIR = Path(__file__).resolve().parents[1] / (os.getenv("YOLO_WEIGHTS_DIR") or "models")
# 업로드된 레인별 가중치 저장소. host dev 는 backend/data/weights, compose 는 env 로
# /app/data/weights 를 주입해 같은 코드가 양쪽에서 동작한다.
WEIGHTS_DIR: Path = Path(
    os.getenv("WEIGHTS_DIR")
    or str(Path(__file__).resolve().parent.parent / "data" / "weights")
)


def _env_float(name: str, default: float) -> tuple[float, str | None]:
    """env float 파싱 — 비숫자/빈값이면 import 실패 대신 안전 기본값으로 폴백."""
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default, None
    try:
        return float(raw), None
    except ValueError:
        return default, f"{name}={raw!r} 가 숫자가 아니라 기본값 {default} 로 폴백"


YOLO_CONF_THRESHOLD, _conf_warn = _env_float("YOLO_CONF_THRESHOLD", 0.5)
YOLO_DEVICE: str = os.getenv("YOLO_DEVICE", "")

# 캡처와 추론 cadence/autotune의 검증된 내부 정책값.
MIN_INFERENCE_INTERVAL: float = 0.01
MAX_INFERENCE_INTERVAL: float = 1.0
INFERENCE_INTERVAL: float = 0.033
CAPTURE_INTERVAL: float = 0.01
MAX_INFER_PER_SEC: float = 52.0
AUTOTUNE_HEADROOM: float = 0.95
AUTOTUNE_EWMA_ALPHA: float = 0.2
AUTOTUNE_MIN_SAMPLES: int = 5
AUTOTUNE_TARGET_FPS_MAX: float = MAX_INFER_PER_SEC

INFERENCE_BATCH_MAX: int = 8
INFERENCE_BATCH_TIMEOUT_SEC: float = 0.008
INFERENCE_AGGREGATE_TIMEOUT_SEC: float = 2.0
INFERENCE_IMGSZ_STAGES: tuple[int, ...] = (320, 416, 512, 640)
ADAPTIVE_DOWNSHIFT_TICKS: int = 2
ADAPTIVE_UPSHIFT_TICKS: int = 5
ADAPTIVE_OVERLOAD_RATIO: float = 0.85
ADAPTIVE_UNDERLOAD_RATIO: float = 0.65

LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()


def setup_logging() -> logging.Logger:
    """애플리케이션 로거 설정"""
    logger = logging.getLogger("forklift-distance")
    logger.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))

    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(
            logging.Formatter("[%(asctime)s] %(levelname)s  %(name)s — %(message)s",
                              datefmt="%Y-%m-%d %H:%M:%S")
        )
        logger.addHandler(handler)

    # 앱 로거 밖 이름으로 로그를 남기는 코드도 같은 수준 · 출력으로 켜야 그 INFO 가 보인다 —
    # 스트리밍 코어(capture · manager)는 rtsp-streaming.*, 추론(worker 등)은 모듈 이름 app.* 과 모델별 inference.worker.*
    for name in ("rtsp-streaming", "app", "inference"):
        core = logging.getLogger(name)
        core.setLevel(logger.level)
        if not core.handlers:
            for h in logger.handlers:
                core.addHandler(h)

    return logger


logger = setup_logging()

if _raw_yolo_model and _raw_yolo_model != YOLO_DEFAULT_MODEL:
    logger.warning(
        "YOLO_DEFAULT_MODEL=%r 가 공식 모델 목록에 없어 %s를 사용합니다",
        _raw_yolo_model, YOLO_DEFAULT_MODEL,
    )
if _raw_max_ipcams != MAX_IPCAMS:
    logger.warning("MAX_IPCAMS=%d → %d 로 보정됨 (허용 범위: 1~64)", _raw_max_ipcams, MAX_IPCAMS)
for _warning in (_conf_warn,):
    if _warning:
        logger.warning("%s", _warning)
