from .base import ModuleDefinition


module = ModuleDefinition(
    key='proposal_builder',
    name='제안서 생성기',
    category='stage_task',
    stage='B',
    order=2,
    mainRole='sales',
    description='제안 내용을 문서로 구성하며 PPT 장표 생성 스킬을 연결할 예정입니다.',
    status="planned",
    skill="PPT 장표 생성",
)
