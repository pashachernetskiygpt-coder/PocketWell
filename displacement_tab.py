# displacement_tab.py
import logging

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QLineEdit, QComboBox,
    QPushButton, QMessageBox
)
from PyQt5.QtCore import Qt

from balance_calc import calculate_balance, render_balance_text

logger = logging.getLogger("WellApp.gui")


class DisplacementTab(QWidget):
    """
    Вкладка 'Отдувка'.

    Идея:
    - выбираем ОДНУ жидкость (одинаковая в трубах и в затрубе),
    - задаём целевое гидростатическое давление на забое (МПа),
    - считаем высоту столба и объёмы в трубах и затрубе,
    - рисуем столбы на схеме (WellScene.draw_fluids).
    """

    def __init__(self, parent=None, fluids=None, trajectory_tab=None, scene=None):
        super().__init__(parent)
        # общий список Fluid (тот же объект, что и в WellApp)
        self.fluids = fluids if fluids is not None else []
        self.trajectory_tab = trajectory_tab  # вкладка траектории
        self.scene = scene                    # ссылка на WellScene для отрисовки

        # сюда WellApp будет записывать суммарную глубину конструкции по MD
        self.construction_depth_md = 0.0

        # результаты последнего расчёта
        self.h_tubing = 0.0
        self.h_annulus = 0.0
        self.v_tubing = 0.0
        self.v_annulus = 0.0

        logger.debug("Инициализация DisplacementTab")
        self.init_ui()

    # ---------- UI ----------

    def init_ui(self):
        layout = QVBoxLayout(self)

        # Целевое давление
        self.input_pressure = QLineEdit()
        self.input_pressure.setPlaceholderText("Целевая гидростатика на забое (МПа)")
        layout.addWidget(self.input_pressure)

        # Отображение TVD
        self.label_tvd = QLabel("TVD: — м")
        layout.addWidget(self.label_tvd)

        # Жидкость (одна и та же в трубах и затрубе)
        layout.addWidget(QLabel("Жидкость (трубы + затруб)"))
        self.combo_fluid = QComboBox()
        layout.addWidget(self.combo_fluid)

        # Кнопка расчёта
        btn_calc = QPushButton("Рассчитать отдувку")
        btn_calc.clicked.connect(self.run_displacement_calc)
        layout.addWidget(btn_calc)

        # Результат
        self.label_result = QLabel()
        self.label_result.setAlignment(Qt.AlignTop)
        self.label_result.setStyleSheet("font-family: Consolas;")
        layout.addWidget(self.label_result)

    # ---------- Работа с траекторией (MD–TVD) ----------

    def _get_md_tvd_points(self):
        """
        Собирает пары (MD, TVD) из таблицы траектории.
        Возвращает список, отсортированный по MD.
        """
        if self.trajectory_tab is None or not hasattr(self.trajectory_tab, "table"):
            logger.warning("_get_md_tvd_points (Отдувка): trajectory_tab или table отсутствует")
            return []

        table = self.trajectory_tab.table
        pts = []
        for row in range(table.rowCount()):
            md_item = table.item(row, 0)   # MD
            tvd_item = table.item(row, 3)  # TVD
            try:
                if not md_item or not tvd_item:
                    continue
                md = float(md_item.text().replace(",", "."))
                tvd = float(tvd_item.text().replace(",", "."))
            except Exception:
                continue
            pts.append((md, tvd))

        pts.sort(key=lambda x: x[0])
        logger.debug("_get_md_tvd_points (Отдувка): собрано %d точек MD–TVD", len(pts))
        return pts

    def get_tvd_for_md(self, md_target: float) -> float:
        """
        Находит TVD для заданной MD (м) по траектории.
        - если md_target меньше минимальной MD → берём первую TVD
        - если больше максимальной MD → берём последнюю TVD
        - иначе линейно интерполируем между ближайшими точками
        """
        pts = self._get_md_tvd_points()
        if not pts:
            logger.warning("get_tvd_for_md (Отдувка): нет точек траектории")
            return 0.0

        if md_target <= pts[0][0]:
            return pts[0][1]
        if md_target >= pts[-1][0]:
            return pts[-1][1]

        for (md1, tvd1), (md2, tvd2) in zip(pts[:-1], pts[1:]):
            if md1 <= md_target <= md2:
                if md2 - md1 <= 0:
                    return tvd1
                k = (md_target - md1) / (md2 - md1)
                return tvd1 + k * (tvd2 - tvd1)

        return pts[-1][1]

    def get_max_tvd(self) -> float:
        pts = self._get_md_tvd_points()
        if not pts:
            logger.debug("get_max_tvd (Отдувка): нет данных по траектории")
            return 0.0
        return pts[-1][1]

    def update_tvd_display(self) -> float:
        """
        Обновляет надпись TVD в зависимости от конструкции.
        - если construction_depth_md > 0 → TVD для этой MD
        - иначе → максимальная TVD по траектории
        """
        pts = self._get_md_tvd_points()
        if not pts:
            self.label_tvd.setText("TVD: — м (траектория не задана)")
            return 0.0

        max_md_traj = pts[-1][0]
        if self.construction_depth_md and self.construction_depth_md > 0:
            md_use = min(self.construction_depth_md, max_md_traj)
            tvd = self.get_tvd_for_md(md_use)
            self.label_tvd.setText(f"TVD: {tvd:.2f} м (MD {md_use:.1f} м)")
            logger.debug(
                "update_tvd_display (Отдувка): TVD=%.2f м для MD=%.1f м "
                "(конструкция=%.1f м, max_MD_траектории=%.1f м)",
                tvd, md_use, self.construction_depth_md, max_md_traj,
            )
            return tvd
        else:
            tvd = pts[-1][1]
            self.label_tvd.setText(f"TVD: {tvd:.2f} м (по максимальной MD траектории)")
            logger.debug(
                "update_tvd_display (Отдувка): TVD=%.2f м по максимальной траектории (MD=%.1f м)",
                tvd, max_md_traj,
            )
            return tvd

    # ---------- Расчёт отдувки ----------

    def run_displacement_calc(self):
        try:
            logger.debug("run_displacement_calc: запуск")

            # Давление
            txt_p = (self.input_pressure.text() or "").strip()
            if not txt_p:
                QMessageBox.warning(self, "Отдувка", "Введите целевое давление (МПа).")
                logger.warning("run_displacement_calc: не введено давление")
                return

            try:
                target_pressure_mpa = float(txt_p.replace(",", "."))
            except ValueError:
                QMessageBox.warning(self, "Отдувка", "Некорректное значение давления.")
                logger.warning("run_displacement_calc: некорректный ввод давления: %s", txt_p)
                return

            target_pressure = target_pressure_mpa * 1e6

            # Траектория
            pts = self._get_md_tvd_points()
            if not pts:
                QMessageBox.warning(
                    self,
                    "Отдувка",
                    "Не задана траектория (вкладка 'Траектория')."
                )
                logger.warning("run_displacement_calc: нет данных по траектории")
                return

            max_md_traj = pts[-1][0]
            max_tvd_traj = pts[-1][1]

            constr_md = self.construction_depth_md or 0.0

            # Выбор MD/TVD для расчёта
            if constr_md <= 0:
                used_md = max_md_traj
                used_tvd = max_tvd_traj
                logger.debug(
                    "run_displacement_calc: глубина конструкции не задана, "
                    "используем максимальную TVD=%.2f м при MD=%.1f м",
                    used_tvd, used_md,
                )
            else:
                if constr_md > max_md_traj + 1e-6:
                    QMessageBox.warning(
                        self,
                        "Отдувка",
                        (
                            "Глубина конструкции (MD = %.1f м) больше максимальной MD "
                            "по траектории (%.1f м).\n"
                            "Будет использована максимальная доступная TVD."
                        ) % (constr_md, max_md_traj)
                    )
                    used_md = max_md_traj
                    used_tvd = max_tvd_traj
                    logger.warning(
                        "run_displacement_calc: MD конструкции=%.1f м > max_MD_траектории=%.1f м, "
                        "используем TVD по максимуму (%.2f м)",
                        constr_md, max_md_traj, used_tvd,
                    )
                else:
                    used_md = constr_md
                    used_tvd = self.get_tvd_for_md(constr_md)
                    logger.debug(
                        "run_displacement_calc: используем TVD=%.2f м для MD конструкции=%.1f м "
                        "(max_MD_траектории=%.1f м)",
                        used_tvd, constr_md, max_md_traj,
                    )

            self.label_tvd.setText(f"TVD: {used_tvd:.2f} м (MD {used_md:.1f} м)")

            if used_tvd <= 0:
                QMessageBox.warning(
                    self,
                    "Отдувка",
                    "Не удалось определить TVD по траектории.\n"
                    "Проверьте данные во вкладке 'Траектория'."
                )
                logger.warning("run_displacement_calc: used_tvd <= 0 (%.3f)", used_tvd)
                return

            # Жидкость
            if not self.fluids:
                QMessageBox.warning(self, "Отдувка", "Сначала добавьте жидкости на вкладке 'Жидкости'.")
                logger.warning("run_displacement_calc: список fluids пуст")
                return

            idx = self.combo_fluid.currentIndex()
            if idx < 0 or idx >= len(self.fluids):
                QMessageBox.warning(self, "Отдувка", "Выберите жидкость.")
                logger.warning(
                    "run_displacement_calc: некорректный индекс жидкости: %s (len=%s)",
                    idx, len(self.fluids)
                )
                return

            fluid = self.fluids[idx]
            logger.debug(
                "run_displacement_calc: fluid=%s (ρ=%.3f)",
                getattr(fluid, "name", "?"),
                getattr(fluid, "density", 0.0),
            )

            # Считаем как в balance_calc, но одна и та же жидкость в трубах и затрубе
            results_core, h_t, h_a, V_t, V_a = calculate_balance(
                target_pressure,
                used_tvd,
                fluid,
                fluid,
            )

            # Добавим шапку, чтобы было понятно, что это отдувка
            header = [
                "🔁 Расчёт отдувки (одна жидкость в трубах и затрубе)",
                f"Целевая гидростатика на забое: {target_pressure_mpa:.2f} МПа",
                "",
            ]
            results = header + results_core

            logger.debug(
                "Результаты расчёта отдувки: h_t=%.2f, h_a=%.2f, V_t=%.3f, V_a=%.3f",
                h_t, h_a, V_t, V_a
            )
            self.label_result.setText(render_balance_text(results))

            self.h_tubing = h_t
            self.h_annulus = h_a
            self.v_tubing = V_t
            self.v_annulus = V_a

            # Рисуем столбы
            if self.scene is not None:
                self.scene.draw_fluids(
                    h_t_md=h_t,
                    h_a_md=h_a,
                    color_t=getattr(fluid, "color", None),
                    color_a=getattr(fluid, "color", None),
                )

        except Exception:
            logger.exception("Ошибка в run_displacement_calc")
            QMessageBox.warning(
                self,
                "Ошибка расчёта отдувки",
                "Произошла непредвиденная ошибка.\nСм. лог для деталей."
            )

    # ---------- Работа со списком жидкостей ----------

    def populate_fluid_combo(self):
        """
        Обновляет комбобокс на основе текущего списка fluids.
        """
        if not hasattr(self, "combo_fluid"):
            logger.debug("populate_fluid_combo: combo_fluid ещё не создан")
            return

        self.combo_fluid.blockSignals(True)
        self.combo_fluid.clear()

        if not self.fluids:
            self.combo_fluid.addItem("Нет жидкостей")
            logger.debug("populate_fluid_combo: fluids пуст, добавлена заглушка")
        else:
            names = [
                f"{f.name or 'Без названия'} — {f.density:.2f} г/см³"
                for f in self.fluids
            ]
            self.combo_fluid.addItems(names)
            logger.debug("populate_fluid_combo: обновлено %s жидкостей", len(self.fluids))

        self.combo_fluid.blockSignals(False)
