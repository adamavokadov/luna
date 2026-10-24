"""Все тексты интерфейса (русский, HTML-разметка). Динамические значения экранируем через q()."""

from __future__ import annotations

from aiogram import html

from skazki_bot.db import repo
from skazki_bot.db.models import Child
from skazki_bot.domain import interests as interest_catalog
from skazki_bot.domain.enums import Gender, TaleLength
from skazki_bot.domain.text import age_label, plural
from skazki_bot.harness.skills import Skill


def q(value: str) -> str:
    return html.quote(value)


# --- Знакомство и анкета ------------------------------------------------------------------------
WELCOME_NEW = (
    "✨ <b>Здравствуйте! Я — сказочник.</b>\n\n"
    "Сочиняю персональные сказки для детей: с именем малыша, его любимыми героями "
    "и в понятном для его возраста стиле.\n\n"
    "Давайте познакомимся с вашим ребёнком — это займёт меньше минуты.\n\n"
    "<i>🔒 Я храню только имя, пол, возраст и интересы ребёнка — они нужны для сказок. "
    "Всё можно удалить командой /delete.</i>"
)
NEED_PROFILE = "Сначала создадим профиль ребёнка — так сказки получатся по-настоящему личными."
ASK_NAME = "Как зовут вашего ребёнка?\n\nНапишите имя — так сказка зазвучит особенно тепло."
BAD_NAME = (
    "Не получилось распознать имя 🤔\n"
    "Напишите, пожалуйста, только имя — буквами, без цифр и символов (например: Маша или Иван)."
)
ASK_GENDER = "Это мальчик или девочка?\n\nНужно, чтобы правильно склонять слова в сказке."
ASK_AGE = "Сколько лет ребёнку?\n\nОт возраста зависят сложность и длина сказки."
ASK_EXTRA = (
    "Хотите добавить что-то своё?\n\n"
    "Например: <i>любит рисовать, боится темноты, дружит с котом Мурзиком</i>.\n"
    "Напишите одним сообщением (до 200 символов) или пропустите."
)
ASK_EXTRA_EDIT = (
    "Напишите, что ещё важно знать о ребёнке (до 200 символов), "
    "или нажмите «Очистить», чтобы убрать заметку."
)
TEXT_ONLY = "Пожалуйста, ответьте текстом 🙂"
USE_BUTTONS = "Выберите вариант кнопкой выше 👆"
UNKNOWN = "Я умею сочинять сказки ✨ Откройте меню и выберите, что почитаем."
STALE_BUTTON = "Эта кнопка уже неактуальна. Откройте меню: /menu"
LIMIT_CHILDREN = "Достигнут лимит профилей. Чтобы добавить нового ребёнка, удалите один из текущих."


def ask_interests(name: str) -> str:
    return (
        f"Что любит <b>{q(name)}</b>? Выберите несколько тем — герои и сюжеты подстроятся.\n\n"
        "Когда закончите, нажмите «Готово»."
    )


def child_card(child: Child) -> str:
    gender = Gender(child.gender)
    lines = [f"{gender.emoji} <b>{q(child.name)}</b>, {age_label(child.age)}"]
    buttons = interest_catalog.buttons_for(child.interests)
    lines.append("🎯 Интересы: " + (", ".join(buttons) if buttons else "не выбраны"))
    if child.extra_interests:
        lines.append("📝 Ещё: " + q(child.extra_interests))
    return "\n".join(lines)


def profile_ready(child: Child) -> str:
    return f"🎉 <b>Профиль готов!</b>\n\n{child_card(child)}\n\nЧто почитаем?"


def profile_text(child: Child, total: int) -> str:
    suffix = (
        f"\n\n<i>Профилей: {total}. Сказки сочиняются для выбранного ребёнка.</i>"
        if total > 1
        else ""
    )
    return f"👶 <b>Профиль ребёнка</b>\n\n{child_card(child)}{suffix}"


def confirm_delete_child(child: Child) -> str:
    return (
        f"Удалить профиль <b>{q(child.name)}</b> вместе со всеми его сказками?\n"
        "Это действие нельзя отменить."
    )


# --- Меню и сказки ------------------------------------------------------------------------------
def menu_text(child: Child, remaining: int | None) -> str:
    text = f"{Gender(child.gender).emoji} <b>{q(child.name)}</b> — что почитаем сегодня?"
    if remaining is not None:
        word = plural(remaining, "сказку", "сказки", "сказок")
        text += f"\n\n<i>Сегодня можно сочинить ещё {remaining} {word}</i>"
    return text


def tale_modes(child: Child, *, bedtime: bool) -> str:
    head = "🌙 <b>Сказка на ночь</b>" if bedtime else "✨ <b>Новая сказка</b>"
    return f"{head} для <b>{q(child.name)}</b>\n\nКак сочиним?"


def formats_text(child: Child, *, bedtime: bool) -> str:
    head = "🌙 <b>Сказка на ночь</b>" if bedtime else "🎨 <b>Формат сказки</b>"
    return f"{head} для <b>{q(child.name)}</b>\n\nВыберите формат — у каждого своя методика:"


def topic_text(skill: Skill, child: Child) -> str:
    prompt = skill.meta.input_prompt or "О чём должна быть сказка?"
    return f"{skill.emoji} <b>{q(skill.title)}</b> для <b>{q(child.name)}</b>\n\n{q(prompt)}"


def parent_note(note: str) -> str:
    return f"💡 <b>Для родителей</b>\n\n{q(note)}"


def classics_list(child: Child) -> str:
    return f"📖 Выберите классическую сказку — расскажу её по-новому для <b>{q(child.name)}</b>:"


def ask_idea(child: Child) -> str:
    return (
        "💭 О чём должна быть сказка?\n\n"
        f"Например: <i>про динозавра, который боится темноты</i> или "
        f"<i>как {q(child.name)} летал на ракете</i>.\n"
        "Напишите одним сообщением (до 200 символов)."
    )


def composing(child: Child, *, bedtime: bool) -> str:
    what = "сказку на ночь" if bedtime else "сказку"
    return f"✨ Сочиняю {what} для <b>{q(child.name)}</b>…"


def limit_reached(limit: int) -> str:
    word = plural(limit, "сказка", "сказки", "сказок")
    return (
        f"На сегодня все {limit} {word} уже рассказаны 🌙\n"
        "Завтра будут новые — а пока можно перечитать любимые в разделе «Мои сказки»."
    )


ALREADY_COMPOSING = "Сказка уже сочиняется — совсем немного терпения ✨"
LLM_FAIL = "Сказочник задумался и не смог закончить сказку 😔\nПопробуйте ещё раз через минутку."
IDEA_TOO_SHORT = "Расскажите чуть подробнее — хотя бы пару слов 🙂"
RATED_UP = "Спасибо! Буду рассказывать похожие 💛"
RATED_DOWN = "Спасибо, учту — в следующий раз попробую по-другому"
ERROR = "Что-то пошло не так 😔 Попробуйте ещё раз или откройте меню: /menu"
NO_TALES = "Здесь пока пусто. Сочиним первую сказку? ✨"


def tales_list(child: Child, total: int) -> str:
    return f"📚 <b>Сказки для {q(child.name)}</b>\nВсего: {total}. Нажмите на название, чтобы перечитать."


# --- Настройки и приватность --------------------------------------------------------------------
def settings_text(length: TaleLength) -> str:
    return (
        "⚙️ <b>Настройки</b>\n\n"
        f"Длина сказок: <b>{length.label.lower()}</b>.\n"
        "Выбор влияет на объём текста — он также зависит от возраста ребёнка."
    )


PRIVACY = (
    "🔒 <b>Приватность</b>\n\n"
    "<b>Что хранится:</b> ваш Telegram-id, профили детей (имя, пол, возраст, интересы) "
    "и тексты созданных сказок.\n"
    "<b>Что не хранится:</b> ваше имя, username, телефон.\n\n"
    "Чтобы сочинить сказку, имя, пол, возраст и интересы ребёнка передаются сервису ИИ-генерации "
    "(Anthropic). Не указывайте фамилию, адрес и другие личные данные.\n\n"
    "Удалить всё можно в любой момент: /delete."
)
DELETE_ASK = "🗑 Удалить <b>все</b> данные — профили детей и сказки?\nЭто действие нельзя отменить."
DELETED = "Готово — все данные удалены. Если захотите вернуться, нажмите /start 🌙"

HELP = (
    "✨ <b>Сказочник</b> — персональные сказки для вашего ребёнка.\n\n"
    "/start — начать или вернуться\n"
    "/menu — главное меню\n"
    "/new — новая сказка\n"
    "/profile — профиль ребёнка\n"
    "/delete — удалить мои данные\n"
    "/cancel — отменить текущее действие\n\n"
    "Форматов много: сказка на ночь, метафорическая (помогает прожить трудную ситуацию), "
    "подготовка к событию, релакс, в стихах, с загадками, смешная, познавательная и другие. "
    "Можно выбрать формат самому, «удивить» — или описать свою идею."
)


# --- Безопасность ---------------------------------------------------------------------------------
IDEA_REJECTED = (
    "Не получилось использовать такое описание 🙏\n"
    "Расскажите своими словами, о чём должна быть сказка: про героя, место или доброе приключение."
)
CRISIS_SUPPORT = (
    "💛 Спасибо, что написали. То, что вы описали, — серьёзная ситуация, и сказка здесь не поможет.\n\n"
    "Если ребёнку или кому-то рядом грозит опасность прямо сейчас — звоните в экстренные службы: 112.\n"
    "Поговорить и получить поддержку можно по единому детскому телефону доверия в России: "
    "8-800-2000-122 (бесплатно и анонимно, для детей, подростков и родителей). "
    "В другой стране обратитесь в местную службу помощи семье и детям.\n\n"
    "Когда станет немного легче, я буду рад сочинить сказку 🌙"
)
GUARD_BLOCKED = (
    "Не получилось подобрать подходящую сказку 😔\n"
    "Попробуйте другой формат или чуть иначе сформулируйте тему."
)


def stats_text(stats: list[repo.SkillUsage]) -> str:
    if not stats:
        return "📊 За последние 7 дней запусков не было."
    lines = ["📊 <b>Форматы за 7 дней</b>"]
    for item in stats:
        lines.append(
            f"<b>{q(item.skill)}</b> — {item.runs} (ок {item.ok}, блок {item.blocked}, "
            f"ошибок {item.errors}) · {item.avg_latency_ms / 1000:.1f} с · "
            f"{item.avg_input_tokens}→{item.avg_output_tokens} ток. · правок {item.revised}"
        )
    return "\n".join(lines)
