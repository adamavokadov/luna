from __future__ import annotations


def plural(n: int, one: str, few: str, many: str) -> str:
    """Русское склонение по числу: 1 год, 2 года, 5 лет."""
    n10, n100 = n % 10, n % 100
    if n10 == 1 and n100 != 11:
        return one
    if 2 <= n10 <= 4 and not 12 <= n100 <= 14:
        return few
    return many


def age_label(age: int) -> str:
    return f"{age} {plural(age, 'год', 'года', 'лет')}"
