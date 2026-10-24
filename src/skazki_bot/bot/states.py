from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class ChildForm(StatesGroup):
    """Анкета ребёнка: используется и для создания, и для правки отдельных полей."""

    name = State()
    gender = State()
    age = State()
    interests = State()
    extra = State()


class IdeaForm(StatesGroup):
    idea = State()
