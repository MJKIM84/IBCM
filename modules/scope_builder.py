from .base import ModuleDefinition


module = ModuleDefinition(
    key='scope_builder',
    name='범위 정의서 작성기',
    category='stage_task',
    stage='B',
    order=5,
    mainRole='delivery',
    description='수행 범위와 제외 범위, 완료 기준을 정리합니다.',
    status="planned",
)
