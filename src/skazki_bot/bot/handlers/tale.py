"""Создание сказок: режимы, меню форматов (навыков), темы, классика, генерация со стримингом, оценка."""

from __future__ import annotations

import contextlib

from aiogram import Bot, F
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.chat_action import ChatActionSender

from skazki_bot.bot import keyboards as kb
from skazki_bot.bot import texts
from skazki_bot.bot.callbacks import MenuCb, RateCb, TaleCb
from skazki_bot.bot.delivery import send_tale
from skazki_bot.bot.handlers.base import new_router
from skazki_bot.bot.handlers.onboarding import begin_create
from skazki_bot.bot.states import IdeaForm
from skazki_bot.bot.utils import chat_id_of, safe_edit, show
from skazki_bot.config import Settings
from skazki_bot.db import repo
from skazki_bot.db.base import SessionFactory
from skazki_bot.db.models import Child, User
from skazki_bot.harness import GuardBlocked, InputRejected, ModelRefused, SkillRegistry
from skazki_bot.harness.guard import screen_free_text
from skazki_bot.llm.base import LLMError
from skazki_bot.llm.sanitize import clean_text
from skazki_bot.logging import get_logger
from skazki_bot.services.streaming import DraftStreamer
from skazki_bot.services.tale_service import (
    AlreadyGenerating,
    ChildNotFound,
    DailyLimitReached,
    TaleRequest,
    TaleService,
)
from skazki_bot.stories.library import load_classics
from skazki_bot.stories.selector import SelectionContext, eligible

router = new_router("tale")
log = get_logger(__name__)

IDEA_MAX_LEN = 200
IDEA_MIN_LEN = 3


async def _active_child(sf: SessionFactory, user_id: int) -> Child | None:
    async with sf.begin() as session:
        return await repo.get_active_child(session, user_id)


# --- Выбор режима -------------------------------------------------------------------------------
async def open_modes(
    event: Message | CallbackQuery,
    bot: Bot,
    state: FSMContext,
    sf: SessionFactory,
    user: User,
    *,
    bedtime: bool,
    fresh: bool = False,
) -> None:
    await state.clear()
    child = await _active_child(sf, user.id)
    if child is None:
        await begin_create(event, bot, state, intro=texts.NEED_PROFILE)
        return
    await show(
        event,
        bot,
        texts.tale_modes(child, bedtime=bedtime),
        kb.tale_modes_kb(bedtime=bedtime),
        fresh=fresh,
    )


@router.message(Command("new"))
async def cmd_new(
    message: Message, bot: Bot, state: FSMContext, sf: SessionFactory, user: User
) -> None:
    await open_modes(message, bot, state, sf, user, bedtime=False)


@router.callback_query(MenuCb.filter(F.action.in_({"new", "bedtime"})))
async def cb_modes(
    callback: CallbackQuery,
    callback_data: MenuCb,
    bot: Bot,
    state: FSMContext,
    sf: SessionFactory,
    user: User,
) -> None:
    await callback.answer()
    await open_modes(
        callback,
        bot,
        state,
        sf,
        user,
        bedtime=callback_data.action == "bedtime",
        fresh=callback_data.fresh,
    )


# --- Меню форматов и тем ------------------------------------------------------------------------
@router.callback_query(TaleCb.filter(F.action == "formats"))
async def cb_formats(
    callback: CallbackQuery,
    callback_data: TaleCb,
    bot: Bot,
    state: FSMContext,
    sf: SessionFactory,
    user: User,
    skills: SkillRegistry,
) -> None:
    await callback.answer()
    child = await _active_child(sf, user.id)
    if child is None:
        await begin_create(callback, bot, state, intro=texts.NEED_PROFILE)
        return
    formats = skills.eligible(child.age, bedtime=callback_data.bedtime, menu_only=True)
    await safe_edit(
        callback,
        bot,
        texts.formats_text(child, bedtime=callback_data.bedtime),
        kb.formats_kb(formats, bedtime=callback_data.bedtime),
    )


@router.callback_query(TaleCb.filter(F.action == "skill"))
async def cb_skill(
    callback: CallbackQuery,
    callback_data: TaleCb,
    bot: Bot,
    state: FSMContext,
    sf: SessionFactory,
    user: User,
    tales: TaleService,
    settings: Settings,
    skills: SkillRegistry,
) -> None:
    child = await _active_child(sf, user.id)
    skill = skills.get(callback_data.skill)
    if (
        child is None
        or skill is None
        or skill not in skills.eligible(child.age, bedtime=callback_data.bedtime)
    ):
        await callback.answer(texts.STALE_BUTTON, show_alert=True)
        return
    await callback.answer()
    if skill.meta.input == "none":
        request = TaleRequest(skill=skill.name, bedtime=callback_data.bedtime)
        await _start(callback, bot, state, child, user, tales, settings, request)
        return
    await safe_edit(
        callback,
        bot,
        texts.topic_text(skill, child),
        kb.topic_kb(skill, bedtime=callback_data.bedtime),
    )


@router.callback_query(TaleCb.filter(F.action == "preset"))
async def cb_preset(
    callback: CallbackQuery,
    callback_data: TaleCb,
    bot: Bot,
    state: FSMContext,
    sf: SessionFactory,
    user: User,
    tales: TaleService,
    settings: Settings,
    skills: SkillRegistry,
) -> None:
    child = await _active_child(sf, user.id)
    skill = skills.get(callback_data.skill)
    presets = skill.presets if skill else ()
    if child is None or skill is None or not 0 <= callback_data.idx < len(presets):
        await callback.answer(texts.STALE_BUTTON, show_alert=True)
        return
    await callback.answer()
    request = TaleRequest(
        skill=skill.name, bedtime=callback_data.bedtime, idea=presets[callback_data.idx]
    )
    await _start(callback, bot, state, child, user, tales, settings, request)


@router.callback_query(TaleCb.filter(F.action == "go"))
async def cb_go(
    callback: CallbackQuery,
    callback_data: TaleCb,
    bot: Bot,
    state: FSMContext,
    sf: SessionFactory,
    user: User,
    tales: TaleService,
    settings: Settings,
    skills: SkillRegistry,
) -> None:
    child = await _active_child(sf, user.id)
    skill = skills.get(callback_data.skill)
    if child is None or skill is None:
        await callback.answer(texts.STALE_BUTTON, show_alert=True)
        return
    await callback.answer()
    request = TaleRequest(skill=skill.name, bedtime=callback_data.bedtime)
    await _start(callback, bot, state, child, user, tales, settings, request)


@router.callback_query(TaleCb.filter(F.action == "free"))
async def cb_free_topic(
    callback: CallbackQuery,
    callback_data: TaleCb,
    bot: Bot,
    state: FSMContext,
    sf: SessionFactory,
    user: User,
    skills: SkillRegistry,
) -> None:
    child = await _active_child(sf, user.id)
    skill = skills.get(callback_data.skill)
    if child is None or skill is None:
        await callback.answer(texts.STALE_BUTTON, show_alert=True)
        return
    await callback.answer()
    await state.set_state(IdeaForm.idea)
    await state.update_data(bedtime=callback_data.bedtime, skill=skill.name)
    await safe_edit(
        callback,
        bot,
        texts.topic_text(skill, child) + "\n\nНапишите одним сообщением (до 200 символов).",
        kb.idea_cancel_kb(bedtime=callback_data.bedtime),
    )


# --- Авто-режим, классика, своя идея -----------------------------------------------------------
@router.callback_query(TaleCb.filter(F.action == "auto"))
async def cb_auto(
    callback: CallbackQuery,
    callback_data: TaleCb,
    bot: Bot,
    state: FSMContext,
    sf: SessionFactory,
    user: User,
    tales: TaleService,
    settings: Settings,
) -> None:
    await callback.answer()
    child = await _active_child(sf, user.id)
    if child is None:
        await begin_create(callback, bot, state, intro=texts.NEED_PROFILE)
        return
    request = TaleRequest(skill=None, bedtime=callback_data.bedtime)
    await _start(callback, bot, state, child, user, tales, settings, request)


@router.callback_query(TaleCb.filter(F.action == "list"))
async def cb_list_classics(
    callback: CallbackQuery,
    callback_data: TaleCb,
    bot: Bot,
    state: FSMContext,
    sf: SessionFactory,
    user: User,
) -> None:
    await callback.answer()
    child = await _active_child(sf, user.id)
    if child is None:
        await begin_create(callback, bot, state, intro=texts.NEED_PROFILE)
        return
    ctx = SelectionContext(age=child.age, bedtime=callback_data.bedtime)
    classics = sorted(eligible(load_classics(), ctx), key=lambda c: c.title)
    await safe_edit(
        callback,
        bot,
        texts.classics_list(child),
        kb.classics_kb(classics, bedtime=callback_data.bedtime),
    )


@router.callback_query(TaleCb.filter(F.action == "pick"))
async def cb_pick_classic(
    callback: CallbackQuery,
    callback_data: TaleCb,
    bot: Bot,
    state: FSMContext,
    sf: SessionFactory,
    user: User,
    tales: TaleService,
    settings: Settings,
) -> None:
    await callback.answer()
    child = await _active_child(sf, user.id)
    if child is None:
        await begin_create(callback, bot, state, intro=texts.NEED_PROFILE)
        return
    request = TaleRequest(
        skill="classic", bedtime=callback_data.bedtime, classic_id=callback_data.seed or None
    )
    await _start(callback, bot, state, child, user, tales, settings, request)


@router.callback_query(TaleCb.filter(F.action == "idea"))
async def cb_idea(
    callback: CallbackQuery,
    callback_data: TaleCb,
    bot: Bot,
    state: FSMContext,
    sf: SessionFactory,
    user: User,
) -> None:
    await callback.answer()
    child = await _active_child(sf, user.id)
    if child is None:
        await begin_create(callback, bot, state, intro=texts.NEED_PROFILE)
        return
    await state.set_state(IdeaForm.idea)
    await state.update_data(bedtime=callback_data.bedtime, skill="")
    await safe_edit(
        callback, bot, texts.ask_idea(child), kb.idea_cancel_kb(bedtime=callback_data.bedtime)
    )


@router.message(IdeaForm.idea, F.text)
async def on_idea(
    message: Message,
    bot: Bot,
    state: FSMContext,
    sf: SessionFactory,
    user: User,
    tales: TaleService,
    settings: Settings,
) -> None:
    idea = clean_text(message.text or "", IDEA_MAX_LEN)
    if len(idea) < IDEA_MIN_LEN:
        await message.answer(texts.IDEA_TOO_SHORT)
        return
    category = screen_free_text(idea).category
    if category == "crisis":
        await state.clear()
        await message.answer(texts.CRISIS_SUPPORT, reply_markup=kb.back_home_kb())
        return
    if category == "injection":
        await message.answer(texts.IDEA_REJECTED)  # состояние сохраняем — можно написать иначе
        return

    data = await state.get_data()
    await state.clear()
    child = await _active_child(sf, user.id)
    if child is None:
        await begin_create(message, bot, state, intro=texts.NEED_PROFILE)
        return
    request = TaleRequest(
        skill=data.get("skill") or None, bedtime=bool(data.get("bedtime")), idea=idea
    )
    status = await message.answer(texts.composing(child, bedtime=request.bedtime))
    await compose(
        bot,
        message.chat.id,
        user_id=user.id,
        child_id=child.id,
        request=request,
        tales=tales,
        settings=settings,
        status=status,
    )


@router.message(IdeaForm.idea)
async def on_idea_not_text(message: Message) -> None:
    await message.answer(texts.TEXT_ONLY)


# --- Генерация ----------------------------------------------------------------------------------
async def _start(
    callback: CallbackQuery,
    bot: Bot,
    state: FSMContext,
    child: Child,
    user: User,
    tales: TaleService,
    settings: Settings,
    request: TaleRequest,
) -> None:
    """Превращает сообщение с кнопкой в статус «Сочиняю…» и запускает генерацию."""
    await state.clear()
    await safe_edit(callback, bot, texts.composing(child, bedtime=request.bedtime))
    status = callback.message if isinstance(callback.message, Message) else None
    await compose(
        bot,
        chat_id_of(callback),
        user_id=user.id,
        child_id=child.id,
        request=request,
        tales=tales,
        settings=settings,
        status=status,
    )


async def compose(
    bot: Bot,
    chat_id: int,
    *,
    user_id: int,
    child_id: int,
    request: TaleRequest,
    tales: TaleService,
    settings: Settings,
    status: Message | None = None,
) -> None:
    """Сочиняет сказку, показывая прогресс, и отправляет результат. Ошибки превращает в понятный текст."""
    streamer = DraftStreamer(bot, chat_id, min_interval=settings.draft_min_interval)
    try:
        async with ChatActionSender.typing(bot=bot, chat_id=chat_id):
            tale = await tales.generate(
                user_id=user_id, child_id=child_id, request=request, on_progress=streamer.push
            )
    except AlreadyGenerating:
        await bot.send_message(chat_id, texts.ALREADY_COMPOSING)
        return
    except DailyLimitReached as exc:
        await bot.send_message(
            chat_id, texts.limit_reached(exc.limit), reply_markup=kb.back_home_kb()
        )
        return
    except ChildNotFound:
        await bot.send_message(chat_id, texts.NEED_PROFILE)
        return
    except InputRejected as exc:
        message = texts.CRISIS_SUPPORT if exc.category == "crisis" else texts.IDEA_REJECTED
        await bot.send_message(chat_id, message, reply_markup=kb.back_home_kb())
        return
    except ModelRefused as exc:
        log.warning("tale_refused_by_model", user_id=user_id, category=exc.category)
        await bot.send_message(chat_id, texts.GUARD_BLOCKED, reply_markup=kb.retry_kb())
        return
    except GuardBlocked:
        log.warning("tale_blocked_by_guard", user_id=user_id)
        await bot.send_message(chat_id, texts.GUARD_BLOCKED, reply_markup=kb.retry_kb())
        return
    except LLMError:
        log.warning("llm_failed", user_id=user_id, exc_info=True)
        await bot.send_message(chat_id, texts.LLM_FAIL, reply_markup=kb.retry_kb())
        return
    finally:
        if status is not None:  # служебное «Сочиняю…» больше не нужно
            with contextlib.suppress(TelegramAPIError):
                await status.delete()
    await send_tale(
        bot,
        chat_id,
        title=tale.title,
        text=tale.text,
        markup=kb.after_tale_kb(tale.id),
        parent_note=tale.parent_note,
    )


# --- Оценка -------------------------------------------------------------------------------------
@router.callback_query(RateCb.filter())
async def cb_rate(
    callback: CallbackQuery, callback_data: RateCb, sf: SessionFactory, user: User
) -> None:
    value = 1 if callback_data.value > 0 else -1
    async with sf.begin() as session:
        await repo.set_rating(session, user.id, callback_data.tale_id, value)
    await callback.answer(texts.RATED_UP if value > 0 else texts.RATED_DOWN)
    if isinstance(callback.message, Message):
        with contextlib.suppress(TelegramBadRequest):
            await callback.message.edit_reply_markup(reply_markup=kb.after_rate_kb())
