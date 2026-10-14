"""업무 모듈을 연결하는 공통 규격.

모듈 실행은 server의 공통 실행 통로를 통해 호출한다. 공통 실행 통로는
module_runs 기록과 artifacts 저장, module.executed 이벤트 발행을 보장한다.
planned 모듈은 run을 호출하지 않고 skipped 기록과 안내만 남긴다.
"""

from dataclasses import dataclass, field
from sqlite3 import Connection
from typing import Any, Awaitable, Callable


@dataclass
class ModuleContext:
    """모듈이 현재 업무와 저장소, 이벤트 발행 통로에 접근하는 문맥.

    run과 render에서는 project, stage, actor, store, emit을 사용한다.
    user와 db는 기존 서버와 모듈의 생성 코드가 계속 동작하도록 유지하며,
    actor와 store는 각각 같은 사용자와 저장소를 가리킨다.
    """

    project: dict[str, Any]
    stage: str
    user: dict[str, Any]
    db: Connection
    emit: Callable[[str, dict[str, Any]], Any]

    @property
    def actor(self) -> dict[str, Any]:
        """현재 행동하는 담당자 정보."""
        return self.user

    @actor.setter
    def actor(self, value: dict[str, Any]) -> None:
        self.user = value

    @property
    def store(self) -> Connection:
        """모듈이 사용하는 저장소 연결."""
        return self.db

    @store.setter
    def store(self, value: Connection) -> None:
        self.db = value


@dataclass
class ModuleResult:
    """실행 결과와 저장할 산출물.

    산출물은 kind, title, location을 가진 사전이다. version과 stage는
    필요할 때 지정하고, 생략하면 공통 실행 통로가 기본값을 채운다.
    공통 실행 통로가 산출물 저장과 artifact.created 이벤트를 처리하므로
    개별 모듈에서 같은 기록을 중복해서 만들 필요가 없다.
    """

    summary: str
    artifacts: list[dict[str, Any]] = field(default_factory=list)


async def planned_run(ctx: ModuleContext) -> ModuleResult:
    """준비 중 모듈의 실제 실행을 막는다."""
    raise RuntimeError("준비 중인 모듈은 실행할 수 없습니다.")


def planned_render(ctx: ModuleContext) -> dict[str, str]:
    """준비 중 카드의 안내를 반환한다."""
    return {"label": "준비 중", "description": "이 모듈의 기능을 준비하고 있습니다."}


@dataclass(frozen=True)
class ModuleDefinition:
    """파일 하나에 선언하는 모듈 객체.

    mainRole은 외부 모듈 규격의 이름이다. 저장할 때는 module_registry의
    main_role 컬럼과 연결한다. run은 비동기 함수이고 render는 카드에
    표시할 label과 description을 가진 사전을 반환한다. skill은 연결할
    기존 스킬의 이름이고, 연결 예정이 없으면 None을 사용한다.
    """

    key: str
    name: str
    category: str
    stage: str | None
    order: int
    mainRole: str | None
    description: str
    status: str = "planned"
    run: Callable[[ModuleContext], Awaitable[ModuleResult]] = planned_run
    render: Callable[[ModuleContext], dict[str, str]] = planned_render
    skill: str | None = None
