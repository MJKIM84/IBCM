from .base import ModuleDefinition


module = ModuleDefinition(
    key='closure_report',
    name='종료 보고 생성기',
    category='stage_task',
    stage='E',
    order=4,
    mainRole='delivery',
    description='종료 보고를 구성하며 PPT 장표 생성 스킬을 연결할 예정입니다.',
    status="planned",
    skill="PPT 장표 생성",
)
