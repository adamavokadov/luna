"""`python -m skazki_bot.harness.skills_cli [каталог…]` — проверка навыков (для авторов и CI)."""

from __future__ import annotations

import sys
from pathlib import Path

from skazki_bot.harness.skills import SkillError, builtin_skills_dir, scan_skills


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    targets = [Path(a) for a in args] or [builtin_skills_dir()]
    failed = False
    for root in targets:
        try:
            skills = scan_skills(root)
        except SkillError as exc:
            print(f"✗ {exc}")
            failed = True
            continue
        for skill in skills:
            refs = f", файлов: {len(skill.references)}" if skill.references else ""
            print(f"✓ {skill.name} ({skill.emoji} {skill.title}){refs}")
        print(f"— {root}: {len(skills)} навыков")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
