"""이메일 연결 자리. 실제 API 연동 시 이 파일의 handle 구현을 교체한다."""

import logging


logger = logging.getLogger(__name__)


def handle(event: dict) -> None:
    """앱 내부 객체 없이 이벤트 하나를 받아 콘솔 로그만 남긴다."""
    logger.info("email 어댑터가 %s 이벤트를 받았음", event["type"])
