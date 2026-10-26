"""Eval-прогон харнесса: каждый формат × эталонные профили детей.

    python -m skazki_bot.evals                    # все форматы
    python -m skazki_bot.evals --skill bedtime    # только выбранные (можно несколько раз)
    python -m skazki_bot.evals --bedtime          # с наложением «на ночь»
    python -m skazki_bot.evals --smoke            # быстрая проверка: 1 ребёнок, 2 сказки (формат и авто)

Показывает объём, число шагов и инструментов, правки, замечания guard-слоя, токены и время.
С LLM_PROVIDER=anthropic тратит реальные токены — запускайте осознанно; с fake работает офлайн.
Код возврата 1, если хоть один запуск закончился ошибкой или блокировкой.
"""

from __future__ import annotations

import argparse
import asyncio

from skazki_bot.config import Settings, get_settings, resolve_thinking
from skazki_bot.domain.enums import Gender
from skazki_bot.harness import (
    ChildSnapshot,
    HarnessError,
    RecentTale,
    RunInput,
    RunRequest,
    SkillRegistry,
    TaleHarness,
)
from skazki_bot.llm import build_llm
from skazki_bot.llm.fake import FakeLLM

SAMPLE_CHILDREN: tuple[ChildSnapshot, ...] = (
    ChildSnapshot("Маша", Gender.GIRL, 4, ("animals", "drawing"), ""),
    ChildSnapshot("Артём", Gender.BOY, 7, ("space", "robots"), ""),
    ChildSnapshot("Соня", Gender.GIRL, 9, ("magic", "music"), "любит читать"),
)
IDEAS: dict[str, str] = {
    "metaphorical": "Боится темноты",
    "life-event": "Поход к врачу",
    "celebration": "День рождения",
    "educational": "Космос",
    "values": "Делиться",
}
RECENT_STUB = (
    RecentTale(
        title="Звёздочка и облачко",
        skill="original",
        rating=1,
        excerpt="Жила-была маленькая звёздочка, которая очень любила слушать колыбельные облаков.",
    ),
)


async def run_evals(
    settings: Settings, only: list[str], *, bedtime: bool, smoke: bool = False
) -> int:
    registry = SkillRegistry.load(settings.skills_dir)
    # Заглушке задержка стриминга в прогоне оценки не нужна — только лишнее ожидание
    llm = FakeLLM(delay=0) if settings.llm_provider == "fake" else build_llm(settings)
    harness = TaleHarness(llm=llm, registry=registry, settings=settings)
    critic = (
        f"{settings.guard_model} effort={settings.guard_effort}"
        if settings.critic_enabled
        else "выкл."
    )
    print(
        f"модель={settings.llm_model} thinking={resolve_thinking(settings.llm_model, settings.llm_thinking)} "
        f"effort={settings.llm_effort} strict_tools={settings.llm_strict_tools} | критик: {critic}\n"
    )
    header = f"{'формат':<14}{'ребёнок':<9}{'слов':>5}{'шаги':>5}{'инстр.':>7}{'правка':>8}{'крит.':>7}  {'замечания':<22}{'ток. in/out':>13}{'сек':>6}"
    print(header)
    print("-" * len(header))
    failures = 0
    for child in SAMPLE_CHILDREN[:1] if smoke else SAMPLE_CHILDREN:
        names: list[str | None] = [
            s.name
            for s in registry.eligible(child.age, bedtime=bedtime)
            if not only or s.name in only
        ]
        if not only:
            names.append(None)  # авто: формат выбирает модель
        if smoke:
            names = ["original", None]  # один явный формат (1 ход) и авто (цикл с инструментом)
        for name in names:
            request = RunRequest(skill=name, bedtime=bedtime, idea=IDEAS.get(name or ""))
            run_input = RunInput(child=child, request=request, recent=RECENT_STUB)
            label = name or "auto"
            try:
                result = await harness.run(run_input)
            except HarnessError as exc:
                failures += 1
                print(f"{label:<14}{child.name:<9}  ✗ {type(exc).__name__}: {exc}")
                continue
            trace = result.trace
            if smoke and settings.critic_enabled and not trace.critic_used:
                # the critic fails open by design; in a smoke run that must not go unnoticed
                failures += 1
                print(f"{label:<14}{child.name:<9}  ✗ критик не отработал (см. лог critic_failed)")
                continue
            tokens = f"{trace.usage.input_tokens}/{trace.usage.output_tokens}"
            issues = ",".join(trace.issues) or "—"
            print(
                f"{label:<14}{child.name:<9}{len(result.body.split()):>5}{trace.steps:>5}"
                f"{len(trace.tool_calls):>7}{'да' if trace.revised else '—':>8}"
                f"{'да' if trace.critic_used else '—':>7}  {issues:<22}{tokens:>13}"
                f"{trace.latency_ms / 1000:>6.1f}"
            )
    print(f"\nОшибок: {failures}")
    return 1 if failures else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Eval-прогон харнесса сказок")
    parser.add_argument("--skill", action="append", default=[], help="имя навыка (можно повторять)")
    parser.add_argument("--bedtime", action="store_true", help="включить наложение «на ночь»")
    parser.add_argument(
        "--smoke",
        action="store_true",
        help="быстрая проверка: 1 ребёнок, формат + авто, критик обязан отработать",
    )
    args = parser.parse_args(argv)
    return asyncio.run(
        run_evals(get_settings(), args.skill, bedtime=args.bedtime, smoke=args.smoke)
    )


if __name__ == "__main__":
    raise SystemExit(main())
