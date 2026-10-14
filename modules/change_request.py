from .base import ModuleDefinition


module = ModuleDefinition(
    key='change_request',
    name='변경 요청 처리기',
    category='stage_task',
    stage='D',
    order=4,
    mainRole='delivery',
    description='변경 요청의 내용과 일정, 비용 영향을 정리합니다.',
    status="planned",
)
