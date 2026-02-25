# fluids.py
"""
Текстовые представления жидкостей (summary-блоки для вывода в GUI).
"""

import logging
from typing import Iterable, Any

logger = logging.getLogger("WellApp.fluids")


def render_fluid_summary(fluids: Iterable[Any]) -> str:
    """
    Формирует текстовый блок с жидкостями для вывода в результаты.

    Ожидает итерируемый объект с элементами, у которых есть поля:
    - name    : str
    - type    : str
    - density : float (г/см³)

    Возвращает одну строку с переводами строк внутри (готово для QLabel / QTextEdit).
    """
    if fluids is None:
        logger.warning("render_fluid_summary: fluids is None, считаем как пустой список")
        fluids = []

    # Пробуем один раз превратить в список, чтобы можно было посчитать len
    try:
        fluids_list = list(fluids)
    except TypeError:
        logger.error("render_fluid_summary: fluids не является итерируемым: %r", fluids)
        return "Жидкости: [ошибка] передан неитерируемый объект"

    lines = [f"Жидкости (создано): {len(fluids_list)} шт."]

    for idx, f in enumerate(fluids_list):
        if f is None:
            msg = f"— [{idx}] [Ошибка: пустой объект]"
            lines.append(msg)
            logger.warning("render_fluid_summary: обнаружен None на позиции %s", idx)
            continue

        name = getattr(f, "name", "Без названия")
        ftype = getattr(f, "type", "?")
        density = getattr(f, "density", 0.0)

        try:
            dens_val = float(density)
            lines.append(f"— {name} [{ftype}]: плотность {dens_val:.2f} г/см³")
        except Exception as e:
            msg = f"— {name} [{ftype}]: ошибка плотности ({e})"
            lines.append(msg)
            logger.warning(
                "render_fluid_summary: не удалось разобрать плотность у '%s' (%r): %s",
                name, density, e
            )

    return "\n".join(lines)
