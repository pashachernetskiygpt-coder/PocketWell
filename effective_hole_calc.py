# effective_hole_calc.py
import math

PI = math.pi

def calc_effective_openhole_diameter_mm(
    pump_rate_m3_min: float,
    pump_time_min: float,
    openhole_length_m: float,
    volume_correction_m3: float = 0.0,
):
    """
    Считает эффективный диаметр открытого ствола по индикаторной пачке.

    Модель:
        V_pumped = Q * t
        V_openhole = V_pumped - V_correction
        D_eff = sqrt(4 * V_openhole / (pi * L_oh))

    Где V_correction — объём, НЕ относящийся к открытому стволу
    (например, часть пути/объёма в трубах, в обсадной и т.п. — если хочешь учитывать).

    Возвращает:
        (D_eff_mm, V_pumped_m3, V_openhole_m3)
    """
    if pump_rate_m3_min <= 0:
        raise ValueError("Q (м³/мин) должно быть > 0")
    if pump_time_min <= 0:
        raise ValueError("t (мин) должно быть > 0")
    if openhole_length_m <= 0:
        raise ValueError("Длина открытого ствола должна быть > 0")

    v_pumped = pump_rate_m3_min * pump_time_min
    v_openhole = v_pumped - max(volume_correction_m3, 0.0)

    if v_openhole <= 0:
        raise ValueError("Получился V_openhole ≤ 0. Проверь Q, t или поправку по объёму.")

    d_eff_m = math.sqrt((4.0 * v_openhole) / (PI * openhole_length_m))
    d_eff_mm = d_eff_m * 1000.0

    return d_eff_mm, v_pumped, v_openhole
