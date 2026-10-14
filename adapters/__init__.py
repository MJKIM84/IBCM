"""이벤트 전달 대상을 설정하고 같은 handle 인터페이스로 어댑터를 제공한다.

어댑터는 id, project_id, type, payload, created_at 필드가 있는 이벤트만 받는다.
앱 객체와 데이터베이스는 전달하지 않는다. 전달 기록은 서버가 관리한다.
"""

from . import email, notion, slack


ADAPTERS = {
    "slack": slack,
    "notion": notion,
    "email": email,
}

EVENT_ROUTES = {
    "project.created": ("notion",),
    "stage.approval_requested": ("slack",),
    "stage.approved": ("slack", "notion", "email"),
    "stage.rejected": ("slack",),
    "module.executed": ("slack",),
    "artifact.created": ("notion",),
}
