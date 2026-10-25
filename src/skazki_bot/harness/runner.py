"""Харнесс: агентный цикл «модель ↔ инструменты» с навыками, guardrails, правкой и трассировкой."""

from __future__ import annotations

import math
import random
import time
from collections.abc import Awaitable, Callable, Sequence
from typing import Any

from skazki_bot.config import Settings
from skazki_bot.domain.age import target_words
from skazki_bot.domain.interests import labels_for, themes_for
from skazki_bot.harness.guard import Issue, check_tale, parse_critic, screen_free_text
from skazki_bot.harness.prompts import (
    CRITIC_SYSTEM,
    LAST_STEP_NOTE,
    build_critic_user,
    build_revision_message,
    build_system,
    build_user_message,
)
from skazki_bot.harness.skills import BEDTIME, Skill, SkillRegistry
from skazki_bot.harness.tools import ToolContext, ToolExecutor, tool_specs_for
from skazki_bot.harness.types import (
    GuardBlocked,
    HarnessError,
    InputRejected,
    RunInput,
    RunResult,
    RunTrace,
)
from skazki_bot.knowledge.tale_kb import (
    FolkToolkit,
    load_folk_toolkit,
    pick_toolkit,
    toolkit_prompt,
)
from skazki_bot.llm.base import ChatLLM, LLMError, Message, TurnResult
from skazki_bot.llm.parse import ParsedTale, parse_tale
from skazki_bot.logging import get_logger
from skazki_bot.stories.library import Classic, get_classic, load_classics
from skazki_bot.stories.selector import SelectionContext, select_classic

log = get_logger(__name__)

ProgressCallback = Callable[[str], Awaitable[None]]
AUTO_TOOLS = ("load_skill", "read_skill_file", "pick_classic", "get_recent_tales")
# Нерешённые замечания этих типов превращаются в блокировку — показывать такую сказку нельзя
ESCALATE_IF_UNRESOLVED = frozenset({"not_russian"})


class TaleHarness:
    def __init__(
        self,
        *,
        llm: ChatLLM,
        registry: SkillRegistry,
        settings: Settings,
        classics: Sequence[Classic] | None = None,
        rng: random.Random | None = None,
        toolkit: FolkToolkit | None = None,
        toolkit_rng: random.Random | None = None,
    ) -> None:
        self._llm = llm
        self.registry = registry
        self._cfg = settings
        self._classics = tuple(classics) if classics is not None else load_classics()
        self._rng = rng or random.Random()
        # A separate generator: picking folk building blocks must not shift classic selection
        self._toolkit = toolkit if toolkit is not None else load_folk_toolkit()
        self._toolkit_rng = toolkit_rng or random.Random()
        self._system = build_system(registry)

    # --- публичный вход ---------------------------------------------------------------------------
    async def run(self, inp: RunInput, on_progress: ProgressCallback | None = None) -> RunResult:
        trace = RunTrace(model=self._cfg.llm_model)
        started = time.monotonic()
        try:
            return await self._run(inp, on_progress, trace)
        except HarnessError as exc:
            exc.trace = trace
            raise
        except LLMError as exc:
            raise HarnessError(str(exc), trace) from exc
        finally:
            trace.latency_ms = int((time.monotonic() - started) * 1000)

    # --- основной алгоритм ------------------------------------------------------------------------
    async def _run(
        self, inp: RunInput, on_progress: ProgressCallback | None, trace: RunTrace
    ) -> RunResult:
        child, req = inp.child, inp.request

        # 1. Входной guard: кризис/инъекции — отказ; чувствительная тема — режим повышенной бережности
        sensitive = False
        for text in (req.idea, child.extra):
            if not text:
                continue
            category = screen_free_text(text).category
            if category in ("crisis", "injection"):
                raise InputRejected(category)
            sensitive = sensitive or category == "sensitive"

        # 2. Навыки: явный выбор — тело сразу в контексте; авто — модель загружает сама
        primary = self._primary(inp)
        overlays = self._overlays(inp, primary)
        explicit = [s for s in (primary, *overlays) if s is not None]
        trace.skills_loaded.extend(s.name for s in explicit)
        trace.overlays.extend(o.name for o in overlays)
        classic = self._classic_for(inp, primary)

        base_words = target_words(child.age, inp.length)
        words = self._words(base_words, explicit)
        budget_words = words if primary is not None else math.ceil(base_words * 1.3)
        max_tokens = min(self._cfg.llm_max_tokens, budget_words * 4 + 600)

        user = build_user_message(
            name=child.name,
            gender=child.gender,
            age=child.age,
            interest_labels=labels_for(list(child.interests)),
            extra=child.extra,
            target_words=words,
            primary=primary,
            overlays=overlays,
            classic=classic,
            idea=req.idea,
            recent_formats=[t.skill for t in inp.recent if t.skill][:3],
            sensitive=sensitive,
            toolkit=self._toolkit_block(inp, primary, sensitive),
        )

        # 3. Инструменты: у явного навыка — принцип наименьших привилегий
        tool_names = self._tool_names(primary, overlays)
        specs = tool_specs_for(tool_names)
        executor = ToolExecutor(
            ToolContext(
                registry=self.registry,
                age=child.age,
                bedtime=req.bedtime,
                classics=self._classics,
                selection=self._selection(inp),
                recent=inp.recent,
                rng=self._rng,
                loaded=trace.skills_loaded,
                words_for=lambda skill: self._words(base_words, [*overlays, skill]),
            )
        )

        messages: list[Message] = [{"role": "user", "content": user}]
        final = await self._agent_loop(messages, specs, executor, max_tokens, on_progress, trace)

        # 4. Проверки, критик и одна правка по замечаниям
        skills = self._loaded_skills(trace)
        needs_note = any(s.meta.parent_note for s in skills)
        target = self._words(base_words, skills)
        parsed = parse_tale(final.text, fallback_title=f"Сказка для {child.name}")
        if not parsed.body:
            raise HarnessError("Модель вернула пустой текст")

        issues = await self._review(inp, parsed, skills, target, needs_note, sensitive, trace)
        revisions = 0
        while revisions < self._cfg.harness_max_revisions and any(
            i.severity in ("fix", "block") for i in issues
        ):
            revisions += 1
            trace.revised = True
            messages.append({"role": "assistant", "content": final.assistant_content})
            messages.append(
                {
                    "role": "user",
                    "content": build_revision_message(
                        [i for i in issues if i.severity != "info"], needs_note=needs_note
                    ),
                }
            )
            revised = await self._turn(messages, specs, max_tokens, on_progress, trace)
            if revised.tool_calls or not revised.text.strip():
                break  # правка не удалась — остаёмся с предыдущей версией
            candidate = parse_tale(revised.text, fallback_title=parsed.title)
            if not candidate.body:
                break
            final, parsed = revised, candidate
            issues = await self._review(inp, parsed, skills, target, needs_note, sensitive, trace)

        trace.issues = [i.code for i in issues]
        blocking = [
            i
            for i in issues
            if i.severity == "block" or (i.severity == "fix" and i.code in ESCALATE_IF_UNRESOLVED)
        ]
        if blocking:
            log.warning("tale_blocked", codes=[i.code for i in blocking])
            raise GuardBlocked(
                "Сказка не прошла проверки: " + ", ".join(i.code for i in blocking), trace
            )

        return RunResult(
            title=parsed.title,
            body=parsed.body,
            parent_note=parsed.parent_note,
            skill=trace.primary_skill,
            seed_id=classic.id if classic else None,
            trace=trace,
        )

    # --- цикл «модель ↔ инструменты» --------------------------------------------------------------
    async def _agent_loop(
        self,
        messages: list[Message],
        specs: Sequence[Any],
        executor: ToolExecutor,
        max_tokens: int,
        on_progress: ProgressCallback | None,
        trace: RunTrace,
    ) -> TurnResult:
        max_steps = self._cfg.harness_max_steps
        for step in range(1, max_steps + 1):
            result = await self._turn(messages, specs, max_tokens, on_progress, trace)
            if not result.tool_calls:
                if not result.text.strip():
                    raise HarnessError("Модель вернула пустой ответ")
                return result

            messages.append({"role": "assistant", "content": result.assistant_content})
            tool_results: list[dict[str, Any]] = []
            for call in result.tool_calls:
                trace.tool_calls.append(call.name)
                output = await executor.run(call)
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": call.id,
                        "content": output.content,
                        "is_error": output.is_error,
                    }
                )
            if step == max_steps - 1:
                tool_results.append({"type": "text", "text": LAST_STEP_NOTE})
            messages.append({"role": "user", "content": tool_results})
        raise HarnessError(f"Агент не завершил работу за {max_steps} шагов")

    async def _turn(
        self,
        messages: Sequence[Message],
        specs: Sequence[Any],
        max_tokens: int,
        on_progress: ProgressCallback | None,
        trace: RunTrace,
    ) -> TurnResult:
        acc = ""  # накапливаем текст ТЕКУЩЕГО хода: у каждого хода свой «черновик»

        async def on_text(delta: str) -> None:
            nonlocal acc
            acc += delta
            if on_progress is not None:
                try:
                    await on_progress(acc)
                except Exception:  # индикатор прогресса не должен ронять генерацию
                    log.warning("progress_callback_failed", exc_info=True)

        trace.steps += 1
        result = await self._llm.turn(
            system=self._system,
            messages=messages,
            tools=specs,
            max_tokens=max_tokens,
            on_text=on_text,
        )
        trace.usage = trace.usage + result.usage
        return result

    # --- проверки качества -------------------------------------------------------------------------
    async def _review(
        self,
        inp: RunInput,
        parsed: ParsedTale,
        skills: Sequence[Skill],
        target: int,
        needs_note: bool,
        sensitive: bool,
        trace: RunTrace,
    ) -> list[Issue]:
        issues = check_tale(
            title=parsed.title,
            body=parsed.body,
            parent_note=parsed.parent_note,
            name=inp.child.name,
            target_words=target,
            needs_note=needs_note,
            sensitive=sensitive,
        )
        if self._cfg.critic_enabled and not any(i.severity == "block" for i in issues):
            issues += await self._critic(inp, parsed, skills, trace)
        return issues

    async def _critic(
        self, inp: RunInput, parsed: ParsedTale, skills: Sequence[Skill], trace: RunTrace
    ) -> list[Issue]:
        try:
            raw, usage = await self._llm.complete(
                system=CRITIC_SYSTEM,
                user=build_critic_user(
                    name=inp.child.name,
                    gender=inp.child.gender,
                    age=inp.child.age,
                    skills=[s.name for s in skills],
                    title=parsed.title,
                    body=parsed.body,
                    note=parsed.parent_note,
                ),
                max_tokens=700,
                model=self._cfg.guard_model,
            )
        except LLMError:
            log.warning("critic_failed", exc_info=True)  # сбой критика не блокирует сказку
            return []
        trace.guard_usage = trace.guard_usage + usage
        trace.critic_used = True
        return parse_critic(raw)

    # --- вспомогательное ----------------------------------------------------------------------------
    def _primary(self, inp: RunInput) -> Skill | None:
        name = inp.request.skill
        if name is None:
            return None
        skill = self.registry.get(name)
        if skill is None:
            raise HarnessError(f"Неизвестный навык «{name}»")
        if not skill.fits_age(inp.child.age):
            raise HarnessError(f"Навык «{name}» не подходит для возраста {inp.child.age}")
        return skill

    def _overlays(self, inp: RunInput, primary: Skill | None) -> list[Skill]:
        if not inp.request.bedtime or (primary is not None and primary.name == BEDTIME):
            return []
        overlay = self.registry.get(BEDTIME)
        return [overlay] if overlay is not None and overlay.meta.overlay else []

    def _toolkit_block(self, inp: RunInput, primary: Skill | None, sensitive: bool) -> str | None:
        """Optional folk building blocks (opening, closing, helper...) from the knowledge base.

        Skipped for emotionally heavy topics: playful formulas would be out of tune there.
        """
        if sensitive:
            return None
        bedtime = inp.request.bedtime or (primary is not None and primary.name == BEDTIME)
        pick = pick_toolkit(
            self._toolkit,
            age=inp.child.age,
            bedtime=bedtime,
            themes=themes_for(list(inp.child.interests)),
            rng=self._toolkit_rng,
        )
        return toolkit_prompt(pick)

    def _selection(self, inp: RunInput) -> SelectionContext:
        return SelectionContext(
            age=inp.child.age,
            themes=themes_for(list(inp.child.interests)),
            seen=inp.seen,
            liked=set(inp.liked),
            disliked=set(inp.disliked),
            bedtime=inp.request.bedtime,
        )

    def _classic_for(self, inp: RunInput, primary: Skill | None) -> Classic | None:
        """Классический сюжет подставляем заранее, когда формат — «классика» (явный выбор в меню)."""
        if primary is None or primary.name != "classic":
            return None
        if inp.request.classic_id and (chosen := get_classic(inp.request.classic_id)):
            return chosen
        return select_classic(self._classics, self._selection(inp), self._rng)

    def _words(self, base: int, skills: Sequence[Skill]) -> int:
        factor = 1.0
        for skill in skills:
            factor *= skill.meta.length_factor
        return max(round(base * factor / 10) * 10, 60)

    def _loaded_skills(self, trace: RunTrace) -> list[Skill]:
        return [s for n in trace.skills_loaded if (s := self.registry.get(n)) is not None]

    def _tool_names(self, primary: Skill | None, overlays: Sequence[Skill]) -> list[str]:
        if primary is None:
            return list(AUTO_TOOLS)
        names = list(primary.allowed_tools)
        has_refs = bool(primary.references) or any(o.references for o in overlays)
        if has_refs and "read_skill_file" not in names:
            names.append("read_skill_file")
        return names
