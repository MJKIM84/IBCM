"""모듈 파일 이름을 한 줄 등록하면 화면과 저장소에 연결한다."""

from importlib import import_module
from inspect import iscoroutinefunction
import re

from .base import ModuleDefinition


# 새 모듈 파일의 확장자를 뺀 이름을 이 목록에 한 줄 추가한다.
MODULE_FILES = (
    "opportunity_card",
    "needs_interview",
    "keyman_map",
    "go_no_go",
    "demo_request",
    "proposal_strategy",
    "proposal_builder",
    "quote_approval",
    "presentation_checklist",
    "scope_builder",
    "effort_estimator",
    "quote_builder",
    "contract_comparison",
    "sales_handover",
    "contract_registration",
    "wbs_builder",
    "kickoff_package",
    "staffing_plan",
    "milestone_tracker",
    "deliverable_checklist",
    "issue_board",
    "change_request",
    "weekly_report",
    "cost_dashboard",
    "delivery_package",
    "acceptance_defects",
    "handover_package",
    "closure_report",
    "project_evaluation",
    "followup_opportunity",
    "minutes",
    "keyman_register",
    "requirements_register",
    "artifact_repository",
    "effort_cost_log",
    "issue_change_history",
)


def _load_modules() -> tuple[ModuleDefinition, ...]:
    definitions = []
    keys = set()
    for filename in MODULE_FILES:
        definition = getattr(import_module(f".{filename}", __package__), "module", None)
        if not isinstance(definition, ModuleDefinition):
            raise ValueError(f"{filename}: module 객체는 ModuleDefinition이어야 합니다.")
        if not re.fullmatch(r"[a-z][a-z0-9_]*", definition.key):
            raise ValueError(f"{filename}: 모듈 키에는 영문 소문자와 숫자, 밑줄만 사용할 수 있습니다.")
        if definition.key in keys:
            raise ValueError(f"중복된 모듈 키입니다: {definition.key}")
        if definition.category == "stage_task":
            if definition.stage not in {"A", "B", "C", "D", "E"}:
                raise ValueError(f"{filename}: 업무 모듈의 단계를 지정해야 합니다.")
            if definition.mainRole not in {"sales", "delivery", "pmo"}:
                raise ValueError(f"{filename}: 업무 모듈의 메인롤을 지정해야 합니다.")
        elif definition.category == "common":
            if definition.stage is not None or definition.mainRole is not None:
                raise ValueError(f"{filename}: 공통 모듈의 단계와 메인롤은 비워야 합니다.")
        else:
            raise ValueError(f"{filename}: 알 수 없는 모듈 분류입니다.")
        if definition.status not in {"planned", "ready", "active"}:
            raise ValueError(f"{filename}: 알 수 없는 모듈 상태입니다.")
        if type(definition.order) is not int or definition.order < 1:
            raise ValueError(f"{filename}: 모듈 순서는 1 이상의 정수여야 합니다.")
        if not definition.name.strip() or not definition.description.strip():
            raise ValueError(f"{filename}: 이름과 설명을 입력해야 합니다.")
        if definition.skill is not None and (
            not isinstance(definition.skill, str) or not definition.skill.strip()
        ):
            raise ValueError(f"{filename}: 연결할 스킬 이름을 입력하거나 None으로 비워야 합니다.")
        if not iscoroutinefunction(definition.run) or not callable(definition.render):
            raise ValueError(f"{filename}: 비동기 run 함수와 render 함수가 필요합니다.")
        keys.add(definition.key)
        definitions.append(definition)
    return tuple(definitions)


MODULES = _load_modules()


def get_modules() -> tuple[ModuleDefinition, ...]:
    """등록된 모듈 정의를 등록 순서대로 반환한다."""
    return MODULES


def get_module(key: str) -> ModuleDefinition:
    """고유 키로 모듈을 찾으며, 없으면 KeyError를 발생시킨다."""
    for definition in MODULES:
        if definition.key == key:
            return definition
    raise KeyError(key)
