# volumes_calc.py
import logging
from typing import Iterable, Any

logger = logging.getLogger("WellApp.volumes")


def _safe_call_volume(obj: Any, method_name: str) -> float:
    """
    Безопасно вызывает метод объёма у объекта (vol_internal / vol_displaced).
    В случае ошибки логирует её и возвращает 0.0.
    """
    try:
        method = getattr(obj, method_name, None)
        if method is None or not callable(method):
            logger.warning(
                "_safe_call_volume: у объекта %r нет метода %s",
                obj, method_name
            )
            return 0.0

        v = float(method())
        if v < 0:
            logger.warning(
                "_safe_call_volume: метод %s у %r вернул отрицательный объём %.6f, принят 0.0",
                method_name, obj, v
            )
            return 0.0
        return v

    except Exception:
        logger.exception(
            "_safe_call_volume: ошибка при вызове %s у объекта %r",
            method_name, obj
        )
        return 0.0


def calculate_volumes(casings: Iterable[Any], bha: Iterable[Any]):
    """
    Выполняет расчёт объёмов конструкции и КНБК.
    casings : список обсадных колонн / интервалов (есть метод vol_internal)
    bha     : список элементов КНБК (есть методы vol_internal и vol_displaced)

    Возвращает список строк для вывода.
    """
    casings = list(casings or [])
    bha = list(bha or [])

    logger.debug(
        "calculate_volumes: старт расчёта, casings=%d, bha=%d",
        len(casings), len(bha)
    )

    # Внутренний объём конструкции
    vol_casings = 0.0
    for c in casings:
        vol_casings += _safe_call_volume(c, "vol_internal")

    # Внутренний объём КНБК
    vol_bha_int = 0.0
    for b in bha:
        vol_bha_int += _safe_call_volume(b, "vol_internal")

    # Вытесняемый объём КНБК
    vol_bha_disp = 0.0
    for b in bha:
        vol_bha_disp += _safe_call_volume(b, "vol_displaced")

    vol_annulus_raw = vol_casings - vol_bha_disp
    vol_annulus = vol_annulus_raw

    warning_lines = []
    if vol_annulus_raw < 0:
        logger.warning(
            "calculate_volumes: затрубный объём получился отрицательным "
            "(V_casings=%.6f, V_bha_disp=%.6f, diff=%.6f). "
            "Принят 0.0 для вывода.",
            vol_casings, vol_bha_disp, vol_annulus_raw
        )
        vol_annulus = 0.0
        warning_lines.append(
            "⚠️ Внимание: расчётный затрубный объём получился отрицательным, "
            "что указывает на некорректные диаметры/длины. Для вывода принят 0.0 м³."
        )

    results = [
        f"Объём конструкции (внутр.): {vol_casings:.3f} м³",
        f"КНБК (внутр.): {vol_bha_int:.3f} м³",
        f"КНБК (вытесняемый): {vol_bha_disp:.3f} м³",
        f"Объём затрубного пространства: {vol_annulus:.3f} м³",
        "",
        "Примечание:",
        "— Диаметры вводятся в миллиметрах, длины — в метрах.",
        "— Для Open Hole используется эффективный диаметр (ID).",
    ]

    # Если были предупреждения — добавим их в конец
    if warning_lines:
        results.append("")
        results.extend(warning_lines)

    logger.debug(
        "calculate_volumes: завершено. V_casings=%.3f, V_bha_int=%.3f, "
        "V_bha_disp=%.3f, V_annulus=%.3f",
        vol_casings, vol_bha_int, vol_bha_disp, vol_annulus
    )

    return results
