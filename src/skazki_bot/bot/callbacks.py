"""Типизированные callback_data (aiogram CallbackData): лимит Telegram — 64 байта."""

from __future__ import annotations

from aiogram.filters.callback_data import CallbackData


class MenuCb(CallbackData, prefix="m"):
    action: str  # home | new | bedtime | profile | tales | cheer | settings
    fresh: bool = False  # True → ответить НОВЫМ сообщением (кнопка стоит под текстом сказки)


class GenderCb(CallbackData, prefix="g"):
    value: str


class AgeCb(CallbackData, prefix="a"):
    value: int


class InterestCb(CallbackData, prefix="i"):
    key: str  # ключ интереса или "_done"


class SkipCb(CallbackData, prefix="sk"):
    step: str = "extra"


class TaleCb(CallbackData, prefix="t"):
    action: str  # auto | formats | skill | preset | free | go | list | pick | idea
    bedtime: bool = False
    seed: str = ""  # id классического сюжета
    skill: str = ""  # имя навыка (формата)
    idx: int = 0  # номер пресета темы


class RateCb(CallbackData, prefix="r"):
    tale_id: int
    value: int  # -1 / +1


class ChildCb(CallbackData, prefix="c"):
    action: str  # view | edit | add | switch_list | switch | del_ask | del_yes
    child_id: int = 0
    field: str = ""  # name | gender | age | interests | extra


class TalesPageCb(CallbackData, prefix="tp"):
    page: int
    fresh: bool = False


class ShowTaleCb(CallbackData, prefix="st"):
    tale_id: int
    page: int = 0


class SettingCb(CallbackData, prefix="s"):
    key: str  # length | privacy | delete_ask | delete_yes
    value: str = ""


class CheerCb(CallbackData, prefix="ch"):
    action: str  # menu | mood | more | freq_menu | freq
    mood: str = ""  # tired | anxious | stuck | proud | any ("" = no preference)
    value: str = ""  # frequency for action=freq: off | weekly | few | daily
    src: str = ""  # where the choice was made: settings | invite | msg
