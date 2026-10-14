from .base import ModuleDefinition


module = ModuleDefinition(
    key='quote_builder',
    name='견적서 생성기',
    category='stage_task',
    stage='B',
    order=7,
    mainRole='pmo',
    description='견적서를 작성하며 견적서 생성 스킬을 연결할 예정입니다.',
    status="planned",
    skill="견적서 생성",
)
