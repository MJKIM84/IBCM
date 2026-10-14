from .base import ModuleDefinition


module = ModuleDefinition(
    key='staffing_plan',
    name='투입 계획 등록',
    category='stage_task',
    stage='C',
    order=6,
    mainRole='pmo',
    description='인력별 투입 시기와 계획 공수를 정리합니다.',
    status="planned",
)
