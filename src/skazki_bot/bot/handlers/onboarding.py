"""Анкета ребёнка (FSM): создание профиля и правка отдельных полей."""

from __future__ import annotations

from typing import Any

from aiogram import Bot, F
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from skazki_bot.bot import keyboards as kb
from skazki_bot.bot import texts
from skazki_bot.bot.callbacks import AgeCb, GenderCb, InterestCb, SkipCb
from skazki_bot.bot.handlers.base import new_router
from skazki_bot.bot.handlers.cheer import invite_once
from skazki_bot.bot.states import ChildForm
from skazki_bot.bot.utils import chat_id_of, safe_edit, show
from skazki_bot.bot.views import profile_view
from skazki_bot.config import Settings
from skazki_bot.db import repo
from skazki_bot.db.base import SessionFactory
from skazki_bot.db.models import Child, User
from skazki_bot.domain.age import MAX_AGE, MIN_AGE
from skazki_bot.domain.enums import Gender
from skazki_bot.domain.interests import BY_KEY
from skazki_bot.harness.guard import screen_free_text
from skazki_bot.llm.sanitize import clean_name, clean_text

router = new_router("onboarding")

EXTRA_MAX_LEN = 200
EDITABLE_FIELDS = frozenset({"name", "gender", "age", "interests", "extra"})


# --- Вход в анкету ------------------------------------------------------------------------------
async def begin_create(
    event: Message | CallbackQuery, bot: Bot, state: FSMContext, *, intro: str | None = None
) -> None:
    await state.clear()
    await state.set_state(ChildForm.name)
    await state.update_data(editing=None, only=False, interests=[])
    text = texts.ASK_NAME if intro is None else f"{intro}\n\n{texts.ASK_NAME}"
    await show(event, bot, text)


async def begin_edit(
    event: Message | CallbackQuery, bot: Bot, state: FSMContext, child: Child, field: str
) -> None:
    await state.clear()
    await state.update_data(editing=child.id, only=True, interests=list(child.interests))
    match field:
        case "name":
            await state.set_state(ChildForm.name)
            await show(event, bot, texts.ASK_NAME)
        case "gender":
            await state.set_state(ChildForm.gender)
            await show(event, bot, texts.ASK_GENDER, kb.gender_kb())
        case "age":
            await state.set_state(ChildForm.age)
            await show(event, bot, texts.ASK_AGE, kb.age_kb())
        case "interests":
            await state.set_state(ChildForm.interests)
            await show(
                event, bot, texts.ask_interests(child.name), kb.interests_kb(child.interests)
            )
        case "extra":
            await state.set_state(ChildForm.extra)
            await show(event, bot, texts.ASK_EXTRA_EDIT, kb.skip_kb("Очистить"))


# --- Завершение ---------------------------------------------------------------------------------
async def _save_edit(
    event: Message | CallbackQuery,
    bot: Bot,
    state: FSMContext,
    sf: SessionFactory,
    settings: Settings,
    user: User,
    **fields: Any,
) -> None:
    data = await state.get_data()
    async with sf.begin() as session:
        await repo.update_child(session, user.id, int(data["editing"]), **fields)
    await state.clear()
    view = await profile_view(sf, settings, user.id)
    if view is None:
        await begin_create(event, bot, state, intro=texts.NEED_PROFILE)
        return
    await show(event, bot, *view)


async def _finish_create(
    event: Message | CallbackQuery,
    bot: Bot,
    state: FSMContext,
    sf: SessionFactory,
    settings: Settings,
    user: User,
    *,
    extra: str,
) -> None:
    data = await state.get_data()
    async with sf.begin() as session:
        too_many = await repo.count_children(session, user.id) >= settings.max_children_per_user
        child = (
            None
            if too_many
            else await repo.create_child(
                session,
                user.id,
                name=data["name"],
                gender=data["gender"],
                age=int(data["age"]),
                interests=list(data.get("interests", [])),
                extra_interests=extra,
            )
        )
    await state.clear()
    if child is None:
        await show(event, bot, texts.LIMIT_CHILDREN, kb.back_home_kb())
        return
    await show(event, bot, texts.profile_ready(child), kb.main_menu())
    await invite_once(bot, chat_id_of(event), sf, user.id)


# --- Шаги ---------------------------------------------------------------------------------------
@router.message(ChildForm.name, F.text)
async def on_name(
    message: Message,
    bot: Bot,
    state: FSMContext,
    sf: SessionFactory,
    settings: Settings,
    user: User,
) -> None:
    name = clean_name(message.text or "")
    if name is None:
        await message.answer(texts.BAD_NAME)
        return
    data = await state.get_data()
    if data.get("only"):
        await _save_edit(message, bot, state, sf, settings, user, name=name)
        return
    await state.update_data(name=name)
    await state.set_state(ChildForm.gender)
    await message.answer(texts.ASK_GENDER, reply_markup=kb.gender_kb())


@router.callback_query(ChildForm.gender, GenderCb.filter())
async def on_gender(
    callback: CallbackQuery,
    callback_data: GenderCb,
    bot: Bot,
    state: FSMContext,
    sf: SessionFactory,
    settings: Settings,
    user: User,
) -> None:
    await callback.answer()
    try:
        gender = Gender(callback_data.value)
    except ValueError:
        return
    data = await state.get_data()
    if data.get("only"):
        await _save_edit(callback, bot, state, sf, settings, user, gender=gender.value)
        return
    await state.update_data(gender=gender.value)
    await state.set_state(ChildForm.age)
    await safe_edit(callback, bot, texts.ASK_AGE, kb.age_kb())


@router.callback_query(ChildForm.age, AgeCb.filter())
async def on_age(
    callback: CallbackQuery,
    callback_data: AgeCb,
    bot: Bot,
    state: FSMContext,
    sf: SessionFactory,
    settings: Settings,
    user: User,
) -> None:
    await callback.answer()
    if not MIN_AGE <= callback_data.value <= MAX_AGE:
        return
    data = await state.get_data()
    if data.get("only"):
        await _save_edit(callback, bot, state, sf, settings, user, age=callback_data.value)
        return
    await state.update_data(age=callback_data.value)
    await state.set_state(ChildForm.interests)
    selected: list[str] = list(data.get("interests", []))
    await safe_edit(callback, bot, texts.ask_interests(data["name"]), kb.interests_kb(selected))


@router.callback_query(ChildForm.interests, InterestCb.filter(F.key != kb.INTEREST_DONE))
async def on_interest_toggle(
    callback: CallbackQuery, callback_data: InterestCb, state: FSMContext
) -> None:
    await callback.answer()
    if callback_data.key not in BY_KEY:
        return
    data = await state.get_data()
    selected: list[str] = list(data.get("interests", []))
    if callback_data.key in selected:
        selected.remove(callback_data.key)
    else:
        selected.append(callback_data.key)
    await state.update_data(interests=selected)
    if isinstance(callback.message, Message):
        await callback.message.edit_reply_markup(reply_markup=kb.interests_kb(selected))


@router.callback_query(ChildForm.interests, InterestCb.filter(F.key == kb.INTEREST_DONE))
async def on_interests_done(
    callback: CallbackQuery,
    bot: Bot,
    state: FSMContext,
    sf: SessionFactory,
    settings: Settings,
    user: User,
) -> None:
    await callback.answer()
    data = await state.get_data()
    selected: list[str] = list(data.get("interests", []))
    if data.get("only"):
        await _save_edit(callback, bot, state, sf, settings, user, interests=selected)
        return
    await state.set_state(ChildForm.extra)
    await safe_edit(callback, bot, texts.ASK_EXTRA, kb.skip_kb())


@router.message(ChildForm.extra, F.text)
async def on_extra_text(
    message: Message,
    bot: Bot,
    state: FSMContext,
    sf: SessionFactory,
    settings: Settings,
    user: User,
) -> None:
    extra = clean_text(message.text or "", EXTRA_MAX_LEN)
    data = await state.get_data()
    category = screen_free_text(extra).category
    if category in ("crisis", "injection"):
        reply = texts.CRISIS_SUPPORT if category == "crisis" else texts.IDEA_REJECTED
        label = "Очистить" if data.get("only") else "Пропустить"
        await message.answer(reply, reply_markup=kb.skip_kb(label))
        return
    if data.get("only"):
        await _save_edit(message, bot, state, sf, settings, user, extra_interests=extra)
    else:
        await _finish_create(message, bot, state, sf, settings, user, extra=extra)


@router.callback_query(ChildForm.extra, SkipCb.filter())
async def on_extra_skip(
    callback: CallbackQuery,
    bot: Bot,
    state: FSMContext,
    sf: SessionFactory,
    settings: Settings,
    user: User,
) -> None:
    await callback.answer()
    data = await state.get_data()
    if data.get("only"):
        await _save_edit(callback, bot, state, sf, settings, user, extra_interests="")
    else:
        await _finish_create(callback, bot, state, sf, settings, user, extra="")


# --- Неподходящий ввод в шагах анкеты -------------------------------------------------------------
@router.message(StateFilter(ChildForm.name, ChildForm.extra))
async def expect_text(message: Message) -> None:
    await message.answer(texts.TEXT_ONLY)


@router.message(StateFilter(ChildForm.gender, ChildForm.age, ChildForm.interests))
async def expect_buttons(message: Message) -> None:
    await message.answer(texts.USE_BUTTONS)
