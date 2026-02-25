# indicator_pill_calc.py
import math
from dataclasses import dataclass
from typing import List, Optional, Tuple

PI = math.pi


@dataclass
class Segment:
    """Сегмент по MD от поверхности вниз."""
    top_md: float
    bottom_md: float
    od_mm: float
    id_mm: float


def _clip_interval(a: float, b: float, x1: float, x2: float) -> float:
    """Длина пересечения [a,b] и [x1,x2]."""
    lo = max(a, x1)
    hi = min(b, x2)
    return max(0.0, hi - lo)


def _area_circle_m2(d_mm: float) -> float:
    """Площадь круга по диаметру в мм -> м²."""
    d_m = max(float(d_mm), 0.0) / 1000.0
    return PI * (d_m ** 2) / 4.0


def _area_annulus_m2(d_outer_mm: float, d_inner_mm: float) -> float:
    """Площадь кольца (наружный - внутренний) в мм -> м²."""
    return max(0.0, _area_circle_m2(d_outer_mm) - _area_circle_m2(d_inner_mm))


def build_string_profile_from_bha(
    bha_rows_top_down: List[Tuple[float, float, float]],
    target_bottom_md: float,
    fallback_od_mm: float,
    fallback_id_mm: float,
) -> List[Segment]:
    """
    bha_rows_top_down: [(length_m, od_mm, id_mm), ...] сверху вниз (как в таблице КНБК).
    Если длины не хватает до target_bottom_md — достраиваем сегментом fallback.
    """
    segs: List[Segment] = []
    md = 0.0

    for length_m, od_mm, id_mm in bha_rows_top_down:
        if length_m <= 0:
            continue
        top = md
        bottom = md + float(length_m)
        segs.append(Segment(top, bottom, float(od_mm), float(id_mm)))
        md = bottom
        if md >= target_bottom_md:
            break

    if md < target_bottom_md:
        segs.append(Segment(md, target_bottom_md, float(fallback_od_mm), float(fallback_id_mm)))

    # подрежем последний сегмент точно до target_bottom_md
    if segs and segs[-1].bottom_md > target_bottom_md:
        segs[-1].bottom_md = target_bottom_md

    return segs


def build_wellbore_profile_from_construction(
    casing_rows_top_down: List[Tuple[float, float]],
    openhole_rows_top_down: List[Tuple[float, float]],
) -> Tuple[List[Segment], List[Segment]]:
    """
    casing_rows_top_down: [(length_m, casing_id_mm), ...] сверху вниз
    openhole_rows_top_down: [(length_m, openhole_id_mm), ...] сверху вниз

    Возвращает:
      casing_profile: Segment(top,bottom, od_mm=ID, id_mm=ID) (od_mm используем как "ID ствола")
      openhole_profile: аналогично (если понадобится позже)
    """
    casing_profile: List[Segment] = []
    openhole_profile: List[Segment] = []

    md = 0.0
    for length_m, id_mm in casing_rows_top_down:
        if length_m <= 0:
            continue
        top = md
        bottom = md + float(length_m)
        casing_profile.append(Segment(top, bottom, float(id_mm), float(id_mm)))
        md = bottom

    for length_m, id_mm in openhole_rows_top_down:
        if length_m <= 0:
            continue
        top = md
        bottom = md + float(length_m)
        openhole_profile.append(Segment(top, bottom, float(id_mm), float(id_mm)))
        md = bottom

    return casing_profile, openhole_profile


def volume_inside_string_m3(string_profile: List[Segment], bottom_md: float) -> float:
    """V внутри колонны (по ID) от устья до bottom_md."""
    v = 0.0
    for s in string_profile:
        L = _clip_interval(s.top_md, s.bottom_md, 0.0, bottom_md)
        if L <= 0:
            continue
        v += _area_circle_m2(s.id_mm) * L
    return v


def _diam_at_md(profile: List[Segment], md: float, attr: str) -> Optional[float]:
    """
    Возвращает od_mm или id_mm для заданной md.
    Берём сегмент, где md попадает в [top, bottom), чтобы не было двойных попаданий на границах.
    """
    for s in profile:
        if s.top_md <= md < s.bottom_md:
            return getattr(s, attr)
    # Если md ровно равен последней границе — вернём из последнего сегмента
    if profile and abs(md - profile[-1].bottom_md) < 1e-9:
        return getattr(profile[-1], attr)
    return None


def volume_annulus_m3(
    well_profile: List[Segment],
    string_profile: List[Segment],
    top_md: float,
) -> float:
    """
    V затруба от устья до top_md (обсаженная часть):
      V = ∫ [ A(ствол_ID) - A(колонна_OD) ] dL

    Правильно считаем по маленьким интервалам между всеми границами сегментов.
    """
    if top_md <= 0:
        return 0.0

    # соберём все границы (0..top_md) из обеих профилей
    cuts = {0.0, float(top_md)}
    for w in well_profile:
        if 0.0 < w.top_md < top_md:
            cuts.add(float(w.top_md))
        if 0.0 < w.bottom_md < top_md:
            cuts.add(float(w.bottom_md))
    for s in string_profile:
        if 0.0 < s.top_md < top_md:
            cuts.add(float(s.top_md))
        if 0.0 < s.bottom_md < top_md:
            cuts.add(float(s.bottom_md))

    grid = sorted(cuts)
    v = 0.0

    for a, b in zip(grid[:-1], grid[1:]):
        L = b - a
        if L <= 0:
            continue
        md_mid = 0.5 * (a + b)

        bore_id_mm = _diam_at_md(well_profile, md_mid, "od_mm")  # od_mm у well_profile = ID ствола
        string_od_mm = _diam_at_md(string_profile, md_mid, "od_mm")

        if bore_id_mm is None or string_od_mm is None:
            # если где-то профиль не покрывает — просто пропускаем этот кусок
            # (лучше так, чем считать чушь)
            continue

        v += _area_annulus_m2(bore_id_mm, string_od_mm) * L

    return v


def string_od_at_md_mm(string_profile: List[Segment], md: float) -> Optional[float]:
    return _diam_at_md(string_profile, md, "od_mm")


def calc_indicator_pill_effective_openhole_mm(
    pump_rate_l_s: float,
    pump_time_min: float,
    top_md: float,
    bottom_md: float,
    casing_profile: List[Segment],
    string_profile: List[Segment],
) -> Tuple[float, float, float, float, float]:
    """
    Полный круг (от начала закачки до первого выхода на поверхность).

    Возвращает:
      D_eff_mm,
      V_pumped_m3,
      V_in_pipe_m3,
      V_ann_cased_m3,
      V_openhole_annulus_m3
    """
    if pump_rate_l_s <= 0 or pump_time_min <= 0:
        raise ValueError("Q и t должны быть > 0.")
    if bottom_md <= top_md:
        raise ValueError("Низ интервала должен быть больше верха.")

    L_oh = bottom_md - top_md
    if L_oh <= 0:
        raise ValueError("Длина open hole должна быть > 0.")

    # V pumped (л/с -> м3/с)
    q_m3_s = float(pump_rate_l_s) / 1000.0
    t_s = float(pump_time_min) * 60.0
    V_pumped = q_m3_s * t_s

    # volumes
    # Внутри трубы считаем до bottom_md (до забоя пачки) — как в твоём ручном примере
    V_in = volume_inside_string_m3(string_profile, bottom_md)

    # Затруб в обсаженной части считаем от 0 до top_md (башмак обсадки)
    V_ann_cased = volume_annulus_m3(casing_profile, string_profile, top_md)

    V_oh = V_pumped - V_in - V_ann_cased

    if V_oh <= 0:
        raise ValueError(
            "По расчёту V_openhole получился <= 0.\n"
            "Проверь Q/t и геометрию (ID трубы/обсадки, OD колонны/КНБК)."
        )

    # OD колонны в openhole (берём на середине интервала)
    md_mid = 0.5 * (top_md + bottom_md)
    od_string_mm = string_od_at_md_mm(string_profile, md_mid)
    if not od_string_mm or od_string_mm <= 0:
        raise ValueError("Не удалось определить OD колонны в интервале open hole (по КНБК/трубе).")

    # Solve for D_eff from annulus volume in open hole:
    # V = (pi/4) * (D_eff^2 - OD^2) * L
    od_m = float(od_string_mm) / 1000.0
    D_eff_m = math.sqrt(od_m**2 + (4.0 * V_oh) / (PI * float(L_oh)))
    D_eff_mm = D_eff_m * 1000.0

    return D_eff_mm, V_pumped, V_in, V_ann_cased, V_oh
