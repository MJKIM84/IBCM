from .base import ModuleDefinition


module = ModuleDefinition(
    key='acceptance_defects',
    name='검수 결함 추적',
    category='stage_task',
    stage='E',
    order=2,
    mainRole='delivery',
    description='검수에서 발견된 결함과 조치 결과를 추적합니다.',
    status="planned",
)
