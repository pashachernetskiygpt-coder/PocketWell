# well_utils.py
import logging
from typing import Optional

from PyQt5.QtWidgets import QTableWidgetItem

logger = logging.getLogger("WellApp.utils")


# ------------------ КОЛОННЫ ------------------

def compute_casing_params(od: Optional[float] = None,
                          id_: Optional[float] = None,
                          wall: Optional[float] = None):
    """
    Восстанавливает недостающий параметр колонны по двум из трёх:
    OD (наружный диаметр), ID (внутренний диаметр), wall (толщина стенки).

    Все размеры — в миллиметрах.
    """
    nums = sum(x is not None for x in (od, id_, wall))
    if nums < 2:
        raise ValueError("Нужно указать минимум два параметра (OD/ID/толщина).")

    if od is None:
        od = id_ + 2 * wall
    elif id_ is None:
        id_ = od - 2 * wall
    elif wall is None:
        wall = (od - id_) / 2

    if id_ is None or od is None or wall is None:
        raise ValueError("Не удалось вычислить параметры колонны.")

    if id_ <= 0 or od <= 0 or wall < 0 or id_ >= od:
        raise ValueError("Параметры колонны некорректны.")

    logger.debug(
        "compute_casing_params -> OD=%.3f, ID=%.3f, wall=%.3f",
        od, id_, wall
    )
    return od, id_, wall


# ------------------ РАБОТА С ЯЧЕЙКАМИ ТАБЛИЦ ------------------

def parse_float_cell(item) -> Optional[float]:
    """
    Безопасно читает float из QTableWidgetItem.
    Пустая/ошибочная ячейка -> None.
    """
    try:
        if item is None:
            return None
        text = (item.text() or "").strip()
        if not text:
            return None
        value = float(text.replace(",", "."))
        return value
    except Exception as e:
        logger.debug("parse_float_cell: не удалось преобразовать %r: %s", item.text() if item else None, e)
        return None


def set_table_item(table, row: int, col: int, value: str):
    """
    Устанавливает текст в ячейку таблицы, создавая QTableWidgetItem при необходимости.
    """
    it = table.item(row, col)
    if it is None:
        it = QTableWidgetItem()
        table.setItem(row, col, it)
    it.setText(value)


# ------------------ НОРМАЛИЗАЦИЯ ТИПОВ КНБК ------------------

BHA_TYPE_MAP = {
    "убт": "Heavy Weight",
    "утяжелённая труба": "Heavy Weight",
    "утяжеленная труба": "Heavy Weight",

    "bt": "Bit",
    "bit": "Bit",
    "долото": "Bit",

    "мотор": "Mud Motor",
    "mud motor": "Mud Motor",

    "стабилизатор": "Stabilizer",
    "stabilizer": "Stabilizer",

    "mwd": "MWD",
    "jar": "Jar",

    "переходник": "Sub",
    "sub": "Sub",

    "бурильная труба": "Drill Pipe",
    "drill pipe": "Drill Pipe",

    "drill collar": "Drill Collar",
    "open hole": "Open Hole",
    "casing": "Casing",
}


def normalize_bha_name(name: str) -> str:
    """
    Нормализует наименование элемента КНБК к стандартному виду,
    используя словарь BHA_TYPE_MAP. Если соответствия нет, возвращает
    исходную строку (обрезанную по краям).
    """
    key = (name or "").strip().lower()
    result = BHA_TYPE_MAP.get(key, (name or "").strip())
    logger.debug("normalize_bha_name: %r -> %r", name, result)
    return result
