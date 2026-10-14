from .base import ModuleDefinition


module = ModuleDefinition(
    key='weekly_report',
    name='주간 보고 생성기',
    category='stage_task',
    stage='D',
    order=5,
    mainRole='delivery',
    description='주간 진행 상황과 다음 주 계획을 정리합니다.',
    status="planned",
)
