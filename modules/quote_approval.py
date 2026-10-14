from .base import ModuleDefinition


module = ModuleDefinition(
    key='quote_approval',
    name='견적 승인 흐름',
    category='stage_task',
    stage='B',
    order=3,
    mainRole='sales',
    description='견적의 검토와 승인 과정을 정리합니다.',
    status="planned",
)
