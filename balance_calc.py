import math
import logging

# Модульный логгер (использует глобальную конфигурацию из logger_setup)
logger = logging.getLogger("WellApp.balance")

# Константы
G = 9.81          # ускорение свободного падения, м/с²
PI = math.pi
TOLERANCE = 1e5   # допуск по «балансу», Па (0.1 МПа)


def calculate_balance(
    reservoir_pressure,
    _=None,
    fluid_tubing=None,
    fluid_annulus=None,
    D_tubing_mm=100.0,   # внутренний диаметр трубы (ID), мм
    D_well_mm=200.0,     # диаметр затруба/ствола, мм
    D_knbk_mm=0.0,       # внешний диаметр КНБК (OD), мм
    L_knbk_m=0.0,        # длина КНБК, м
    max_tvd_m=None       # максимальная доступная TVD пласта, м
):
    """
    Расчёт равновесия и объёмов жидкости в трубах и затрубе.

    Физическая модель:

    - Пластовое давление P_res задано на глубине H = max_tvd_m (TVD пласта).
    - В трубах стоит однородная жидкость плотностью rho_t.
    - В затрубе стоит однородная жидкость плотностью rho_a.
    - Высоты h_t, h_a считаются как ВЫСОТА СТОЛБА ОТ ЗАБОЯ ВВЕРХ,
      создающего гидростатическое давление на пласте:
          p_t = rho_t * g * h_t
          p_a = rho_a * g * h_a
    - «Требуемая» высота для точного баланса:
          h_req = P_res / (rho * g)
      Если h_req > H, то физически вся колонна заполнена (h = H),
      но давление на пласте всё равно ≠ P_res (недодавление/перегрузка).

    Аргументы:
    - reservoir_pressure : float
        Пластовое давление, Па.
    - max_tvd_m : float
        Вертикальная глубина пласта (TVD), м.
    - fluid_tubing, fluid_annulus :
        Объекты с атрибутом density (г/см³) для труб и затруба.
    - D_tubing_mm : float
        Внутренний диаметр трубы (ID), мм.
    - D_well_mm : float
        Диаметр ствола/затруба, мм.
    - D_knbk_mm : float
        Внешний диаметр КНБК (OD), мм.
    - L_knbk_m : float
        Длина КНБК, м (учёт вытеснения объёма в трубах).

    Возвращает:
    - results : list[str] — текстовый отчёт (только строки)
    - h_t : float — высота столба жидкости в трубах от забоя вверх (м)
    - h_a : float — высота столба жидкости в затрубе от забоя вверх (м)
    - V_t : float — объём жидкости в трубах (м³)
    - V_a : float — объём жидкости в затрубе (м³)
    """
    logger.debug("=== Запуск calculate_balance ===")
    logger.debug(
        "Входные: P_res=%s, max_tvd_m=%s, D_tubing_mm=%s, D_well_mm=%s, "
        "D_knbk_mm=%s, L_knbk_m=%s",
        reservoir_pressure, max_tvd_m, D_tubing_mm, D_well_mm, D_knbk_mm, L_knbk_m
    )

    # На случай старого вызова, когда второй аргумент был TVD
    if (max_tvd_m is None or max_tvd_m <= 0) and _ not in (None, 0):
        try:
            max_tvd_m = float(_)
            logger.debug("max_tvd_m взят из второго позиционного аргумента: %s", max_tvd_m)
        except Exception:
            pass

    results = []

    try:
        # --- Проверка исходных данных ---

        if reservoir_pressure is None or reservoir_pressure <= 0:
            msg = "❌ Ошибка: пластовое давление должно быть положительным"
            results.append(msg)
            logger.warning(msg)
            return results, 0.0, 0.0, 0.0, 0.0

        if fluid_tubing is None or fluid_annulus is None:
            msg = "❌ Ошибка: не заданы жидкости для труб и/или затруба"
            results.append(msg)
            logger.warning(msg)
            return results, 0.0, 0.0, 0.0, 0.0

        # Плотности (г/см³ → кг/м³)
        rho_t = (getattr(fluid_tubing, "density", 0.0) or 0.0) * 1000.0
        rho_a = (getattr(fluid_annulus, "density", 0.0) or 0.0) * 1000.0
        logger.debug("Плотности: rho_t=%s, rho_a=%s", rho_t, rho_a)

        if rho_t <= 0 or rho_a <= 0:
            msg = "❌ Ошибка: плотность одной из жидкостей равна нулю или не задана"
            results.append(msg)
            logger.warning(msg)
            return results, 0.0, 0.0, 0.0, 0.0

        H = max_tvd_m if (max_tvd_m is not None and max_tvd_m > 0) else None

        # --- Требуемые высоты от забоя вверх для точного баланса с пластом ---

        h_req_t = reservoir_pressure / (rho_t * G)
        h_req_a = reservoir_pressure / (rho_a * G)
        logger.debug("Требуемые высоты: h_req_t=%s, h_req_a=%s", h_req_t, h_req_a)

        # Фактические высоты (ограничиваем TVD пласта, если задана)
        if H is not None:
            h_t = min(h_req_t, H)
            h_a = min(h_req_a, H)
        else:
            h_t = h_req_t
            h_a = h_req_a

        logger.debug("Фактические высоты (с учётом TVD): h_t=%s, h_a=%s", h_t, h_a)

        # Давление на пласте от каждого столба
        p_t = rho_t * G * h_t
        p_a = rho_a * G * h_a

        diff_t = reservoir_pressure - p_t  # + → недодавление, - → перегрузка
        diff_a = reservoir_pressure - p_a
        diff_channels = abs(p_t - p_a)

        logger.debug(
            "Давления на пласте: p_t=%s, p_a=%s, diff_t=%s, diff_a=%s, diff_channels=%s",
            p_t, p_a, diff_t, diff_a, diff_channels
        )

        # --- Геометрия для объёмов ---
        D_t_id = D_tubing_mm / 1000.0
        D_w = D_well_mm / 1000.0
        D_k_od = max(D_knbk_mm, 0.0) / 1000.0
        L_knbk_m = max(L_knbk_m, 0.0)

        logger.debug(
            "Геометрия (м): D_t_id=%s, D_w=%s, D_k_od=%s, L_knbk_m=%s",
            D_t_id, D_w, D_k_od, L_knbk_m
        )

        if D_t_id <= 0 or D_w <= 0:
            msg = "❌ Ошибка: диаметры должны быть положительными"
            results.append(msg)
            logger.warning(msg)
            return results, h_t, h_a, 0.0, 0.0

        if D_w <= D_t_id:
            msg = "❌ Ошибка: диаметр затруба должен быть больше внутреннего диаметра трубы"
            results.append(msg)
            logger.warning(msg)
            return results, h_t, h_a, 0.0, 0.0

        if D_k_od >= D_t_id and D_k_od > 0:
            msg = "❌ Ошибка: диаметр КНБК не может быть ≥ внутреннего диаметра трубы"
            results.append(msg)
            logger.warning(msg)
            return results, h_t, h_a, 0.0, 0.0

        # --- Объём в трубах ---
        if D_k_od > 0.0 and L_knbk_m > 0.0:
            # участок, где КНБК внутри трубы
            h_bha = min(h_t, L_knbk_m)
            # столб выше КНБК (если есть)
            h_above = max(h_t - L_knbk_m, 0.0)

            A_annular = (PI / 4.0) * (D_t_id**2 - D_k_od**2)  # кольцевое "труба–КНБК"
            A_full = (PI / 4.0) * D_t_id**2                  # полное сечение трубы

            V_t = A_annular * h_bha + A_full * h_above
            logger.debug("Площади: A_annular=%s, A_full=%s; V_t=%s", A_annular, A_full, V_t)
        else:
            A_full = (PI / 4.0) * D_t_id**2
            V_t = A_full * h_t
            logger.debug("Площадь трубы A_full=%s; V_t=%s", A_full, V_t)

        # --- Объём в затрубе ---
        A_annulus = (PI / 4.0) * (D_w**2 - D_t_id**2)
        V_a = A_annulus * h_a
        logger.debug("Площадь затруба A_annulus=%s; V_a=%s", A_annulus, V_a)

        # --- Формирование отчёта ---

        results.append("🔧 Высота столба жидкости (от забоя вверх):")
        results.append(f"  Трубы (h_t): {h_t:.2f} м")
        results.append(f"  Затруб (h_a): {h_a:.2f} м")

        if H is not None:
            results.append(f"Максимальная TVD пласта: {H:.2f} м")
            if h_req_t > H or h_req_a > H:
                results.append(
                    "ℹ️ Требуемая высота столба для точного баланса "
                    "превышает TVD пласта — колонна полностью заполнена."
                )

        results.append("")
        results.append("📍 Давление на пласте:")
        results.append(
            f"  Пластовое: {reservoir_pressure:.1f} Па ({reservoir_pressure/1e6:.2f} МПа)"
        )

        # Трубы
        results.append(
            f"  В трубах: {p_t:.1f} Па ({p_t/1e6:.2f} МПа), "
            f"∆P = {diff_t/1e6:.2f} МПа "
            f"({'недодавление' if diff_t > TOLERANCE else 'перегрузка' if diff_t < -TOLERANCE else 'в допуске'})"
        )

        # Затруб
        results.append(
            f"  В затрубе: {p_a:.1f} Па ({p_a/1e6:.2f} МПа), "
            f"∆P = {diff_a/1e6:.2f} МПа "
            f"({'недодавление' if diff_a > TOLERANCE else 'перегрузка' if diff_a < -TOLERANCE else 'в допуске'})"
        )

        # Разность между каналами
        results.append(
            f"Разность давлений между трубами и затрубом: "
            f"{diff_channels:.1f} Па ({diff_channels/1e6:.2f} МПа)"
        )

        results.append("")
        results.append("📦 Объёмы жидкости:")
        results.append(f"  В трубах: {V_t:.2f} м³")
        results.append(f"  В затрубе: {V_a:.2f} м³")
        results.append(f"  Общий объём: {V_t + V_a:.2f} м³")

        # Контроль типов для безопасного join
        bad_types = [type(x).__name__ for x in results if not isinstance(x, str)]
        if bad_types:
            logger.error("results содержит не-строчные элементы: %s", bad_types)
            results = [x if isinstance(x, str) else str(x) for x in results]

        logger.debug("=== Расчёт calculate_balance завершён успешно ===")
        return results, h_t, h_a, V_t, V_a

    except Exception:
        logger.exception("Необработанная ошибка в calculate_balance")
        raise


def render_balance_text(results):
    """
    Безопасно формирует текст для GUI из списка результатов.
    Гарантирует, что join получит только строки; логирует проблему, если встречаются другие типы.
    """
    if not isinstance(results, (list, tuple)):
        logger.error("render_balance_text: ожидался list/tuple, получено %s", type(results).__name__)
        return str(results)

    non_str = [i for i, x in enumerate(results) if not isinstance(x, str)]
    if non_str:
        logger.warning("render_balance_text: элементы не-строки на позициях %s", non_str)
    safe_lines = [x if isinstance(x, str) else str(x) for x in results]
    return "\n".join(safe_lines)
