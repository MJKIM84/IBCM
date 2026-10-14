from .base import ModuleDefinition


module = ModuleDefinition(
    key='handover_package',
    name='인수인계 패키지 생성',
    category='stage_task',
    stage='E',
    order=3,
    mainRole='delivery',
    description='운영 담당자에게 전달할 자료와 안내를 정리합니다.',
    status="planned",
)
