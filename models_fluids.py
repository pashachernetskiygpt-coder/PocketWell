# models_fluids.py
import logging
from dataclasses import dataclass
from typing import Optional

from PyQt5.QtGui import QColor

logger = logging.getLogger("WellApp.fluids_model")


@dataclass
class Fluid:
    """
    Модель жидкости, общая для всего приложения.
    """
    name: str
    type: str
    density: float          # г/см³
    comment: str = ""
    color: Optional[QColor] = None


# Базовые цвета по типам жидкостей
_BASE_COLORS = {
    "Раствор": QColor(0, 120, 255),
    "Буфер":   QColor(0, 180, 0),
    "Цемент":  QColor(255, 140, 0),
}


def fluid_color_by_index_for_type(fluid_type: str, index: int) -> QColor:
    """
    Возвращает QColor для жидкости заданного типа и индекса строки.

    fluid_type: строка, например "Раствор", "Буфер", "Цемент".
    index: номер строки (0, 1, 2, ...), по нему немного сдвигаем оттенок,
           чтобы растворы 1/2/3 друг от друга отличались.
    """
    try:
        base = _BASE_COLORS.get(fluid_type, QColor(150, 150, 150))

        hsv = base.getHsv()
        if not isinstance(hsv, tuple) or len(hsv) != 4:
            logger.error(
                "fluid_color_by_index_for_type: некорректный HSV для типа %r: %r",
                fluid_type,
                hsv,
            )
            return QColor(150, 150, 150)

        h, s, v, a = hsv
        # сдвиг оттенка для разных строк
        hue_shift = (index * 10) % 360
        new_hue = (h + hue_shift) % 360

        return QColor.fromHsv(new_hue, s, v, a)

    except Exception as e:
        logger.exception(
            "fluid_color_by_index_for_type: ошибка при расчёте цвета для типа %r, index=%r: %s",
            fluid_type,
            index,
            e,
        )
        return QColor(150, 150, 150)
