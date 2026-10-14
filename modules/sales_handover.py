from .base import ModuleDefinition


module = ModuleDefinition(
    key='sales_handover',
    name='영업 이관서 자동 생성',
    category='stage_task',
    stage='C',
    order=2,
    mainRole='sales',
    description='영업에서 수행으로 전달할 약속과 맥락을 정리합니다.',
    status="planned",
)
