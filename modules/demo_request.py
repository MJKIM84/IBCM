from .base import ModuleDefinition


module = ModuleDefinition(
    key='demo_request',
    name='데모 요청서와 샘플 접수',
    category='stage_task',
    stage='A',
    order=5,
    mainRole='sales',
    description='시연 요청과 검토할 샘플의 접수 내역을 정리합니다.',
    status="planned",
)
