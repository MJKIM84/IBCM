from .base import ModuleDefinition


module = ModuleDefinition(
    key='issue_board',
    name='이슈 보드',
    category='stage_task',
    stage='D',
    order=3,
    mainRole='delivery',
    description='진행 중인 이슈와 담당자, 처리 상태를 정리합니다.',
    status="planned",
)
