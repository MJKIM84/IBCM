from .base import ModuleDefinition


module = ModuleDefinition(
    key='delivery_package',
    name='인도 패키지 생성',
    category='stage_task',
    stage='E',
    order=1,
    mainRole='delivery',
    description='고객에게 전달할 최종 산출물을 묶어 정리합니다.',
    status="planned",
)
