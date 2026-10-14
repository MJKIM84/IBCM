from .base import ModuleDefinition


module = ModuleDefinition(
    key='followup_opportunity',
    name='후속 사업 기회 생성',
    category='stage_task',
    stage='E',
    order=6,
    mainRole='pmo',
    description='종료 후 이어갈 고객의 필요와 사업 기회를 정리합니다.',
    status="planned",
)
