# indicator_pill_tab.py
import logging
from typing import Callable, List, Optional, Tuple

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QMessageBox, QGroupBox, QFormLayout, QComboBox
)
from PyQt5.QtCore import Qt

from indicator_pill_calc import (
    Segment,
    build_string_profile_from_bha,
    calc_indicator_pill_effective_openhole_mm,
)

logger = logging.getLogger("WellApp.indicator_pill")


class IndicatorPillTab(QWidget):
    """
    Вкладка "Индикаторная пачка" (полный круг).

    Ввод:
      - Q (л/с)
      - t (мин) — от начала закачки до выхода пачки на поверхность (полный круг)
      - выбор интервала Open Hole (если их несколько)
      - fallback труба (OD/ID) на случай, если КНБК не расписана до нужной глубины

    Расчёт учитывает:
      V_pumped = Q*t
      V_in_pipe (ID колонны по профилю)
      V_annulus_cased (ID обсадки - OD колонны) до top_md
      V_openhole_annulus = V_pumped - V_in_pipe - V_annulus_cased
      D_eff из V_openhole_annulus
    """

    def __init__(
        self,
        parent=None,
        # callback: () -> list of intervals: [(row_index, top_md, bottom_md, nominal_id_mm, current_eff_id_mm)]
        get_openhole_intervals_cb: Optional[Callable[[], List[Tuple[int, float, float, Optional[float], Optional[float]]]]] = None,
        # callback: () -> (casing_profile: List[Segment], bha_rows_top_down: List[(L,OD,ID)])
        get_geometry_cb: Optional[Callable[[], Tuple[List[Segment], List[Tuple[float, float, float]]]]] = None,
        # callback: (row_index:int, d_eff_mm: float) -> None
        apply_openhole_id_cb: Optional[Callable[[int, float], None]] = None,
    ):
        super().__init__(parent)

        self.get_openhole_intervals_cb = get_openhole_intervals_cb
        self.get_geometry_cb = get_geometry_cb
        self.apply_openhole_id_cb = apply_openhole_id_cb

        self._intervals: List[Tuple[int, float, float, Optional[float], Optional[float]]] = []
        self.last_result = None  # (row_index, d_eff_mm, ...)

        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)

        # --- Исходные данные ---
        box_in = QGroupBox("Исходные данные")
        form = QFormLayout(box_in)

        self.edit_q = QLineEdit()
        self.edit_q.setPlaceholderText("Напр. 30")
        form.addRow("Производительность Q, л/с:", self.edit_q)

        self.edit_t = QLineEdit()
        self.edit_t.setPlaceholderText("Напр. 96")
        form.addRow("Время t, мин (полный круг):", self.edit_t)

        # интервал OH
        row_oh = QHBoxLayout()
        self.combo_oh = QComboBox()
        self.btn_refresh_oh = QPushButton("Обновить из конструкции")
        self.btn_refresh_oh.clicked.connect(self.refresh_openhole_list)

        row_oh.addWidget(self.combo_oh, 1)
        row_oh.addWidget(self.btn_refresh_oh)
        form.addRow("Интервал Open Hole:", row_oh)

        # fallback drill string
        row_ds = QHBoxLayout()
        self.edit_fallback_od = QLineEdit("127.0")
        self.edit_fallback_id = QLineEdit("100.0")
        self.edit_fallback_od.setMaximumWidth(120)
        self.edit_fallback_id.setMaximumWidth(120)
        row_ds.addWidget(QLabel("OD, мм:"))
        row_ds.addWidget(self.edit_fallback_od)
        row_ds.addSpacing(12)
        row_ds.addWidget(QLabel("ID, мм:"))
        row_ds.addWidget(self.edit_fallback_id)
        row_ds.addStretch(1)
        form.addRow("Труба по умолчанию:", row_ds)

        layout.addWidget(box_in)

        # --- Кнопки ---
        row_btn = QHBoxLayout()
        btn_calc = QPushButton("Рассчитать Dэфф")
        btn_calc.clicked.connect(self.on_calc)

        self.btn_apply = QPushButton("Применить в Open Hole (Эфф. ID)")
        self.btn_apply.setEnabled(False)
        self.btn_apply.clicked.connect(self.on_apply)

        row_btn.addWidget(btn_calc)
        row_btn.addWidget(self.btn_apply)
        layout.addLayout(row_btn)

        # --- Вывод ---
        self.lbl_out = QLabel("Результаты будут здесь")
        self.lbl_out.setAlignment(Qt.AlignTop)
        self.lbl_out.setStyleSheet("font-family: Consolas;")
        layout.addWidget(self.lbl_out)

        layout.addStretch(1)

        # первичная подгрузка списка OH
        self.refresh_openhole_list()

    def refresh_openhole_list(self):
        """Заполняем выпадающий список интервалов Open Hole из конструкции."""
        self.combo_oh.blockSignals(True)
        self.combo_oh.clear()
        self._intervals = []

        if not self.get_openhole_intervals_cb:
            self.combo_oh.addItem("Нет связи с конструкцией")
            self.combo_oh.blockSignals(False)
            return

        try:
            intervals = self.get_openhole_intervals_cb() or []
            self._intervals = intervals

            if not intervals:
                self.combo_oh.addItem("Open Hole не найден")
            else:
                for (row_idx, top_md, bottom_md, nominal_id, eff_id) in intervals:
                    base = f"{top_md:.0f}–{bottom_md:.0f} м"
                    if eff_id and eff_id > 0:
                        txt = f"{base}  |  IDэфф: {eff_id:.1f} мм"
                    elif nominal_id and nominal_id > 0:
                        txt = f"{base}  |  IDном: {nominal_id:.1f} мм"
                    else:
                        txt = base
                    self.combo_oh.addItem(txt)

        except Exception as e:
            logger.exception("refresh_openhole_list error")
            self.combo_oh.addItem("Ошибка чтения Open Hole")
            QMessageBox.warning(self, "Индикаторная пачка", str(e))

        self.combo_oh.blockSignals(False)

    def _get_selected_interval(self):
        idx = self.combo_oh.currentIndex()
        if idx < 0 or idx >= len(self._intervals):
            return None
        return self._intervals[idx]

    def on_calc(self):
        try:
            if not self.get_geometry_cb:
                QMessageBox.warning(self, "Индикаторная пачка", "Нет связи с геометрией (callback не задан).")
                return

            sel = self._get_selected_interval()
            if not sel:
                QMessageBox.warning(self, "Индикаторная пачка", "Выберите интервал Open Hole.")
                return

            row_idx, top_md, bottom_md, nominal_id, eff_id = sel

            q_l_s = float((self.edit_q.text() or "").replace(",", "."))
            t_min = float((self.edit_t.text() or "").replace(",", "."))

            fallback_od = float((self.edit_fallback_od.text() or "").replace(",", "."))
            fallback_id = float((self.edit_fallback_id.text() or "").replace(",", "."))

            if fallback_id <= 0 or fallback_od <= 0 or fallback_id >= fallback_od:
                QMessageBox.warning(self, "Индикаторная пачка", "Проверь трубу по умолчанию: OD>0, ID>0 и ID<OD.")
                return

            # берём геометрию из приложения
            casing_profile, bha_rows_top_down = self.get_geometry_cb()
            if not casing_profile:
                QMessageBox.warning(self, "Индикаторная пачка", "Не удалось получить обсаженный профиль (обсадка).")
                return

            # строим профиль колонны до bottom_md
            string_profile = build_string_profile_from_bha(
                bha_rows_top_down=bha_rows_top_down,
                target_bottom_md=bottom_md,
                fallback_od_mm=fallback_od,
                fallback_id_mm=fallback_id,
            )

            D_eff_mm, V_pumped, V_in, V_ann_cased, V_oh = calc_indicator_pill_effective_openhole_mm(
                pump_rate_l_s=q_l_s,
                pump_time_min=t_min,
                top_md=top_md,
                bottom_md=bottom_md,
                casing_profile=casing_profile,
                string_profile=string_profile,
            )

            self.last_result = (row_idx, D_eff_mm, V_pumped, V_in, V_ann_cased, V_oh, top_md, bottom_md)
            self.btn_apply.setEnabled(True)

            lines = []
            lines.append("🧪 Индикаторная пачка — расчёт Dэфф (полный круг)")
            lines.append("")
            lines.append(f"Интервал Open Hole: {top_md:.2f}–{bottom_md:.2f} м  (L = {bottom_md-top_md:.2f} м)")
            lines.append("")
            lines.append(f"Q = {q_l_s:.2f} л/с  (= {q_l_s/1000.0:.3f} м³/с)")
            lines.append(f"t = {t_min:.2f} мин  (= {t_min*60.0:.0f} c)")
            lines.append(f"Vпрокач = {V_pumped:.3f} м³")
            lines.append("")
            lines.append("Разложение объёма полного круга:")
            lines.append(f"  V внутри колонны (до {bottom_md:.0f} м): {V_in:.3f} м³")
            lines.append(f"  V затруба в обсаженной части (до {top_md:.0f} м): {V_ann_cased:.3f} м³")
            lines.append(f"  V затруба в Open Hole: {V_oh:.3f} м³")
            lines.append("")
            lines.append(f"✅ Dэфф(open hole) = {D_eff_mm:.1f} мм")

            self.lbl_out.setText("\n".join(lines))

            logger.info(
                "IndicatorPill: row=%s D_eff=%.1f mm | V_pumped=%.3f V_in=%.3f V_ann_cased=%.3f V_oh=%.3f",
                row_idx, D_eff_mm, V_pumped, V_in, V_ann_cased, V_oh
            )

        except Exception as e:
            logger.exception("on_calc error")
            QMessageBox.warning(self, "Индикаторная пачка", str(e))
            self.btn_apply.setEnabled(False)
            self.last_result = None

    def on_apply(self):
        if not self.last_result:
            return
        if not self.apply_openhole_id_cb:
            QMessageBox.information(self, "Индикаторная пачка", "Нет связи с конструкцией (callback не задан).")
            return

        row_idx, d_eff_mm = int(self.last_result[0]), float(self.last_result[1])

        try:
            self.apply_openhole_id_cb(row_idx, d_eff_mm)
            QMessageBox.information(self, "Индикаторная пачка", f"Эфф. ID Open Hole обновлён: {d_eff_mm:.1f} мм")
        except Exception as e:
            logger.exception("on_apply error")
            QMessageBox.warning(self, "Индикаторная пачка", str(e))
