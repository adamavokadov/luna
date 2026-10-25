from __future__ import annotations

from collections.abc import Mapping, Sequence

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from skazki_bot.bot import texts
from skazki_bot.bot.callbacks import (
    AgeCb,
    CheerCb,
    ChildCb,
    GenderCb,
    InterestCb,
    MenuCb,
    RateCb,
    SettingCb,
    ShowTaleCb,
    SkipCb,
    TaleCb,
    TalesPageCb,
)
from skazki_bot.cheer.compose import MOODS
from skazki_bot.cheer.schedule import FREQUENCIES
from skazki_bot.db.models import Child, Tale
from skazki_bot.domain.age import MAX_AGE, MIN_AGE
from skazki_bot.domain.enums import Gender, TaleLength
from skazki_bot.domain.interests import INTERESTS
from skazki_bot.harness.skills import Skill
from skazki_bot.stories.library import Classic

INTEREST_DONE = "_done"
TALES_PAGE_SIZE = 5


def home_button() -> InlineKeyboardButton:
    return InlineKeyboardButton(text="🏠 Меню", callback_data=MenuCb(action="home").pack())


def back_home_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[home_button()]])


# --- Главное меню -------------------------------------------------------------------------------
def main_menu() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="✨ Новая сказка", callback_data=MenuCb(action="new"))
    b.button(text="🌙 Сказка на ночь", callback_data=MenuCb(action="bedtime"))
    b.button(text="👶 Профиль ребёнка", callback_data=MenuCb(action="profile"))
    b.button(text="📚 Мои сказки", callback_data=MenuCb(action="tales"))
    b.button(text="💛 Тёплые слова", callback_data=MenuCb(action="cheer"))
    b.button(text="⚙️ Настройки", callback_data=MenuCb(action="settings"))
    b.adjust(2, 2, 2)
    return b.as_markup()


# --- Анкета -------------------------------------------------------------------------------------
def gender_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for gender in Gender:
        b.button(
            text=f"{gender.emoji} {gender.label.capitalize()}",
            callback_data=GenderCb(value=gender.value),
        )
    b.adjust(2)
    return b.as_markup()


def age_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for age in range(MIN_AGE, MAX_AGE + 1):
        b.button(text=str(age), callback_data=AgeCb(value=age))
    b.adjust(3)
    return b.as_markup()


def interests_kb(selected: Sequence[str]) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for interest in INTERESTS:
        mark = "✅ " if interest.key in selected else ""
        b.button(text=f"{mark}{interest.button}", callback_data=InterestCb(key=interest.key))
    b.adjust(2)
    b.row(
        InlineKeyboardButton(
            text="✅ Готово" + (f" ({len(selected)})" if selected else ""),
            callback_data=InterestCb(key=INTEREST_DONE).pack(),
        )
    )
    return b.as_markup()


def skip_kb(label: str = "Пропустить") -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text=label, callback_data=SkipCb())
    return b.as_markup()


# --- Сказки -------------------------------------------------------------------------------------
def tale_modes_kb(*, bedtime: bool) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="🎲 Удиви меня", callback_data=TaleCb(action="auto", bedtime=bedtime))
    b.button(text="🎨 Выбрать формат", callback_data=TaleCb(action="formats", bedtime=bedtime))
    b.button(text="📖 Классика по-новому", callback_data=TaleCb(action="list", bedtime=bedtime))
    b.button(text="💭 Своя идея", callback_data=TaleCb(action="idea", bedtime=bedtime))
    b.adjust(1)
    b.row(home_button())
    return b.as_markup()


def _modes_back(*, bedtime: bool) -> InlineKeyboardButton:
    return InlineKeyboardButton(
        text="← Назад", callback_data=MenuCb(action="bedtime" if bedtime else "new").pack()
    )


def formats_kb(skills: Sequence[Skill], *, bedtime: bool) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for skill in skills:
        b.button(
            text=skill.button,
            callback_data=TaleCb(action="skill", skill=skill.name, bedtime=bedtime),
        )
    b.adjust(2)
    b.row(_modes_back(bedtime=bedtime))
    return b.as_markup()


def topic_kb(skill: Skill, *, bedtime: bool) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for index, preset in enumerate(skill.presets):
        b.button(
            text=preset,
            callback_data=TaleCb(action="preset", skill=skill.name, idx=index, bedtime=bedtime),
        )
    b.adjust(1)
    b.row(
        InlineKeyboardButton(
            text="✍️ Своя тема",
            callback_data=TaleCb(action="free", skill=skill.name, bedtime=bedtime).pack(),
        )
    )
    if skill.meta.input == "optional":
        b.row(
            InlineKeyboardButton(
                text="🎲 Без темы",
                callback_data=TaleCb(action="go", skill=skill.name, bedtime=bedtime).pack(),
            )
        )
    b.row(
        InlineKeyboardButton(
            text="← К форматам",
            callback_data=TaleCb(action="formats", bedtime=bedtime).pack(),
        )
    )
    return b.as_markup()


def classics_kb(classics: Sequence[Classic], *, bedtime: bool) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for classic in classics:
        b.button(
            text=classic.title,
            callback_data=TaleCb(action="pick", seed=classic.id, skill="classic", bedtime=bedtime),
        )
    b.adjust(2)
    b.row(_modes_back(bedtime=bedtime))
    return b.as_markup()


def idea_cancel_kb(*, bedtime: bool) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[_modes_back(bedtime=bedtime)]])


def after_tale_kb(tale_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="👍 Понравилась", callback_data=RateCb(tale_id=tale_id, value=1))
    b.button(text="👎 Не очень", callback_data=RateCb(tale_id=tale_id, value=-1))
    b.button(text="✨ Ещё сказку", callback_data=MenuCb(action="new", fresh=True))
    b.button(text="🏠 Меню", callback_data=MenuCb(action="home", fresh=True))
    b.adjust(2, 2)
    return b.as_markup()


def after_rate_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="✨ Ещё сказку", callback_data=MenuCb(action="new", fresh=True))
    b.button(text="🏠 Меню", callback_data=MenuCb(action="home", fresh=True))
    b.adjust(2)
    return b.as_markup()


def retry_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="🔁 Попробовать снова", callback_data=MenuCb(action="new"))
    b.button(text="🏠 Меню", callback_data=MenuCb(action="home"))
    b.adjust(2)
    return b.as_markup()


# --- Профиль ------------------------------------------------------------------------------------
def profile_kb(child: Child, *, total: int, can_add: bool) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for field, label in (
        ("name", "✏️ Имя"),
        ("age", "✏️ Возраст"),
        ("gender", "✏️ Пол"),
        ("interests", "✏️ Интересы"),
        ("extra", "✏️ Заметка"),
    ):
        b.button(text=label, callback_data=ChildCb(action="edit", child_id=child.id, field=field))
    b.adjust(2)
    if can_add:
        b.row(
            InlineKeyboardButton(
                text="➕ Добавить ребёнка", callback_data=ChildCb(action="add").pack()
            )
        )
    if total > 1:
        b.row(
            InlineKeyboardButton(
                text="🔄 Сменить ребёнка", callback_data=ChildCb(action="switch_list").pack()
            )
        )
    b.row(
        InlineKeyboardButton(
            text="🗑 Удалить профиль",
            callback_data=ChildCb(action="del_ask", child_id=child.id).pack(),
        )
    )
    b.row(home_button())
    return b.as_markup()


def switch_child_kb(children: Sequence[Child]) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for child in children:
        mark = "✅ " if child.is_active else ""
        b.button(
            text=f"{mark}{Gender(child.gender).emoji} {child.name}",
            callback_data=ChildCb(action="switch", child_id=child.id),
        )
    b.adjust(1)
    b.row(InlineKeyboardButton(text="← Назад", callback_data=MenuCb(action="profile").pack()))
    return b.as_markup()


def confirm_delete_child_kb(child_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="🗑 Да, удалить", callback_data=ChildCb(action="del_yes", child_id=child_id))
    b.button(text="Отмена", callback_data=MenuCb(action="profile"))
    b.adjust(2)
    return b.as_markup()


# --- История ------------------------------------------------------------------------------------
def tales_list_kb(
    tales: Sequence[Tale],
    *,
    page: int,
    total: int,
    emoji_by_skill: Mapping[str, str] | None = None,
) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    emoji = emoji_by_skill or {}
    for tale in tales:
        icon = emoji.get(tale.skill or "") or ("🌙" if tale.bedtime else "📖")
        title = tale.title if len(tale.title) <= 40 else tale.title[:39] + "…"
        b.button(text=f"{icon} {title}", callback_data=ShowTaleCb(tale_id=tale.id, page=page))
    b.adjust(1)
    pages = max((total + TALES_PAGE_SIZE - 1) // TALES_PAGE_SIZE, 1)
    nav: list[InlineKeyboardButton] = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="◀️", callback_data=TalesPageCb(page=page - 1).pack()))
    if page + 1 < pages:
        nav.append(InlineKeyboardButton(text="▶️", callback_data=TalesPageCb(page=page + 1).pack()))
    if nav:
        b.row(*nav)
    b.row(home_button())
    return b.as_markup()


def tale_view_kb(page: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="← К списку", callback_data=TalesPageCb(page=page, fresh=True).pack()
                ),
                InlineKeyboardButton(
                    text="🏠 Меню", callback_data=MenuCb(action="home", fresh=True).pack()
                ),
            ]
        ]
    )


# --- Настройки ----------------------------------------------------------------------------------
def settings_kb(current: TaleLength, cheer_freq: str | None = None) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for length in TaleLength:
        mark = "✅ " if length is current else ""
        b.button(
            text=f"{mark}{length.label}", callback_data=SettingCb(key="length", value=length.value)
        )
    b.adjust(3)
    if cheer_freq is not None:
        label = texts.CHEER_FREQ_SHORT.get(cheer_freq, "выкл")
        b.row(
            InlineKeyboardButton(
                text=f"💛 Тёплые слова: {label}", callback_data=CheerCb(action="freq_menu").pack()
            )
        )
    b.row(
        InlineKeyboardButton(text="🔒 Приватность", callback_data=SettingCb(key="privacy").pack())
    )
    b.row(
        InlineKeyboardButton(
            text="🗑 Удалить мои данные", callback_data=SettingCb(key="delete_ask").pack()
        )
    )
    b.row(home_button())
    return b.as_markup()


def privacy_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="← Назад", callback_data=MenuCb(action="settings").pack())],
            [home_button()],
        ]
    )


def confirm_delete_data_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="🗑 Да, удалить всё", callback_data=SettingCb(key="delete_yes"))
    b.button(text="Отмена", callback_data=MenuCb(action="home"))
    b.adjust(2)
    return b.as_markup()


# --- Луна: тёплые слова -------------------------------------------------------------------------
def cheer_moods_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for mood in (*MOODS, "any"):
        b.button(
            text=texts.CHEER_MOOD_LABELS[mood], callback_data=CheerCb(action="mood", mood=mood)
        )
    b.adjust(1)
    b.row(home_button())
    return b.as_markup()


def cheer_after_kb(mood: str = "") -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="💛 Ещё", callback_data=CheerCb(action="more", mood=mood))
    b.button(text="🌙 Сказку", callback_data=MenuCb(action="new", fresh=True))
    b.button(text="🏠 Меню", callback_data=MenuCb(action="home", fresh=True))
    b.adjust(3)
    return b.as_markup()


def cheer_message_kb() -> InlineKeyboardMarkup:
    """Under a proactive message: another word, a tale, and an always-visible way to stop."""
    b = InlineKeyboardBuilder()
    b.button(text="💛 Ещё", callback_data=CheerCb(action="more"))
    b.button(text="🌙 Сказку", callback_data=MenuCb(action="new", fresh=True))
    b.button(text="🔕 Не присылать", callback_data=CheerCb(action="freq", value="off", src="msg"))
    b.adjust(2, 1)
    return b.as_markup()


def cheer_offer_kb(mood: str) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="💛 Да, пожалуйста", callback_data=CheerCb(action="mood", mood=mood))
    b.button(text="🏠 Меню", callback_data=MenuCb(action="home"))
    b.adjust(2)
    return b.as_markup()


def cheer_invite_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(
        text="💛 Раз в неделю", callback_data=CheerCb(action="freq", value="weekly", src="invite")
    )
    b.button(text="🌿 Чаще", callback_data=CheerCb(action="freq", value="few", src="invite"))
    b.button(text="Не сейчас", callback_data=CheerCb(action="freq", value="off", src="invite"))
    b.adjust(2, 1)
    return b.as_markup()


def cheer_freq_kb(current: str) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for freq in FREQUENCIES:
        mark = "✅ " if freq == current else ""
        b.button(
            text=f"{mark}{texts.CHEER_FREQ_LABELS[freq]}",
            callback_data=CheerCb(action="freq", value=freq, src="settings"),
        )
    b.adjust(1)
    b.row(InlineKeyboardButton(text="← Назад", callback_data=MenuCb(action="settings").pack()))
    b.row(home_button())
    return b.as_markup()
