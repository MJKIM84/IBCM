from .base import ModuleDefinition


module = ModuleDefinition(
    key='wbs_builder',
    name='WBS 생성기',
    category='stage_task',
    stage='C',
    order=4,
    mainRole='delivery',
    description='작업 분해 구조를 만들며 WBS 생성 스킬을 연결할 예정입니다.',
    status="planned",
    skill="WBS 생성",
)
