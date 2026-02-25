import math
import logging
from dataclasses import dataclass

logger = logging.getLogger("WellApp.geom")


@dataclass
class Casing:
    """
    Описание интервала конструкции (колонна или открытый ствол).

    Параметры хранятся в миллиметрах и метрах, как в исходном коде:
    - od : внешний диаметр, мм
    - id : внутренний диаметр, мм
    - wall : толщина стенки, мм
    - length : длина участка, м
    - name : произвольное имя/обозначение
    - typ : тип ("Casing", "Open Hole" и т.п.)
    """
    od: float          # внешний диаметр, мм
    id: float          # внутренний диаметр, мм
    wall: float        # толщина стенки, мм
    length: float      # длина, м
    name: str = "Casing"
    typ: str = "Casing"

    def __init__(
        self,
        od_mm: float,
        id_mm: float,
        wall_mm: float,
        length_m: float,
        name: str = "Casing",
        typ: str = "Casing",
    ) -> None:
        # Приводим к float и делаем лёгкую проверку,
        # но не бросаем ошибки, чтобы не ломать GUI.
        self.typ = typ
        self.name = name
        self.od = float(od_mm) if od_mm is not None else 0.0
        self.id = float(id_mm) if id_mm is not None else 0.0
        self.wall = float(wall_mm) if wall_mm is not None else 0.0
        self.length = float(length_m) if length_m is not None else 0.0

        if self.length < 0:
            logger.warning("Casing '%s': отрицательная длина %.3f м, принята 0.0", self.name, self.length)
            self.length = 0.0

        if self.id >= self.od and self.od > 0:
            logger.warning(
                "Casing '%s': ID >= OD (id=%.3f мм, od=%.3f мм) — проверьте данные",
                self.name, self.id, self.od
            )

    def vol_internal(self) -> float:
        """
        Внутренний объём колонны / открытого ствола, м³.
        """
        radius_m = self.id / 1000.0 / 2.0
        return math.pi * radius_m**2 * self.length


class BHAElement:
    """
    Элемент КНБК.

    Параметры:
    - name : название элемента
    - length : длина, м
    - od : внешний диаметр, мм
    - id : внутренний диаметр, мм
    """

    def __init__(self, name: str, length_m: float, od_mm: float, id_mm: float) -> None:
        self.name = name
        self.length = float(length_m) if length_m is not None else 0.0
        self.od = float(od_mm) if od_mm is not None else 0.0
        self.id = float(id_mm) if id_mm is not None else 0.0

        if self.length < 0:
            logger.warning("BHAElement '%s': отрицательная длина %.3f м, принята 0.0", self.name, self.length)
            self.length = 0.0

        if self.id >= self.od and self.od > 0:
            logger.warning(
                "BHAElement '%s': ID >= OD (id=%.3f мм, od=%.3f мм) — проверьте данные",
                self.name, self.id, self.od
            )

    def vol_displaced(self) -> float:
        """
        Вытесняемый объём (по внешнему диаметру), м³.
        """
        radius_m = self.od / 1000.0 / 2.0
        return math.pi * radius_m**2 * self.length

    def vol_internal(self) -> float:
        """
        Внутренний объём (по внутреннему диаметру), м³.
        """
        radius_m = self.id / 1000.0 / 2.0
        return math.pi * radius_m**2 * self.length
