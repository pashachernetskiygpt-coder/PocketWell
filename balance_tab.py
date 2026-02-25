import logging

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QLineEdit, QComboBox,
    QPushButton, QMessageBox
)
from PyQt5.QtCore import Qt

from balance_calc import calculate_balance, render_balance_text
from well_utils import parse_float_cell  # используем общий парсер ячеек

logger = logging.getLogger("WellApp.gui")


class BalanceTab(QWidget):
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

        logger.debug("Инициализация BalanceTab")
        self.init_ui()

    # ---------- UI ----------

    def init_ui(self):
        layout = QVBoxLayout(self)

        # Пластовое давление
        self.input_pressure = QLineEdit()
        self.input_pressure.setPlaceholderText("Пластовое давление (МПа)")
        layout.addWidget(self.input_pressure)

        # Отображение TVD
        self.label_tvd = QLabel("TVD: — м")
        layout.addWidget(self.label_tvd)

        # Жидкость в трубах
        layout.addWidget(QLabel("Жидкость в трубах"))
        self.combo_tubing = QComboBox()
        layout.addWidget(self.combo_tubing)

        # Жидкость в затрубе
        layout.addWidget(QLabel("Жидкость в затрубе"))
        self.combo_annulus = QComboBox()
        layout.addWidget(self.combo_annulus)

        # Кнопка расчёта
        btn_calc = QPushButton("Рассчитать равновесие")
        btn_calc.clicked.connect(self.run_balance_calc)
        layout.addWidget(btn_calc)

        # Результат
        self.label_balance = QLabel()
        self.label_balance.setAlignment(Qt.AlignTop)
        self.label_balance.setStyleSheet("font-family: Consolas;")
        layout.addWidget(self.label_balance)

    # ---------- Вспомогательные методы по траектории ----------

    def _get_md_tvd_points(self):
        """
        Собирает пары (MD, TVD) из таблицы траектории.
        Возвращает список, отсортированный по MD.
        """
        if self.trajectory_tab is None or not hasattr(self.trajectory_tab, "table"):
            logger.warning("_get_md_tvd_points: trajectory_tab или table отсутствует")
            return []

        table = self.trajectory_tab.table
        pts = []
        for row in range(table.rowCount()):
            md_item = table.item(row, 0)  # MD
            tvd_item = table.item(row, 3)  # TVD
            md = parse_float_cell(md_item)
            tvd = parse_float_cell(tvd_item)
            if md is None or tvd is None:
                continue
            pts.append((md, tvd))

        pts.sort(key=lambda x: x[0])
        logger.debug("_get_md_tvd_points: собранo %d точек MD–TVD", len(pts))
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
            logger.warning("get_tvd_for_md: нет точек траектории")
            return 0.0

        # граничные случаи
        if md_target <= pts[0][0]:
            return pts[0][1]
        if md_target >= pts[-1][0]:
            return pts[-1][1]

        # поиск интервала
        for (md1, tvd1), (md2, tvd2) in zip(pts[:-1], pts[1:]):
            if md1 <= md_target <= md2:
                if md2 - md1 <= 0:
                    return tvd1
                k = (md_target - md1) / (md2 - md1)
                tvd = tvd1 + k * (tvd2 - tvd1)
                return tvd

        # на всякий случай
        return pts[-1][1]

    def get_max_tvd(self) -> float:
        """
        Максимальная TVD по траектории (последняя точка).
        """
        pts = self._get_md_tvd_points()
        if not pts:
            logger.debug("get_max_tvd: нет данных по траектории")
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
                "update_tvd_display: TVD=%.2f м для MD=%.1f м (конструкция=%.1f м, max_MD_траектории=%.1f м)",
                tvd, md_use, self.construction_depth_md, max_md_traj,
            )
            return tvd
        else:
            tvd = pts[-1][1]
            self.label_tvd.setText(f"TVD: {tvd:.2f} м (по максимальной MD траектории)")
            logger.debug(
                "update_tvd_display: TVD=%.2f м по максимальной траектории (MD=%.1f м)",
                tvd, max_md_traj,
            )
            return tvd

    # ---------- Расчёт равновесия ----------

    def run_balance_calc(self):
        try:
            logger.debug("run_balance_calc: запуск")

            # Давление
            txt_p = (self.input_pressure.text() or "").strip()
            if not txt_p:
                QMessageBox.warning(self, "Равновесие", "Введите пластовое давление (МПа).")
                logger.warning("run_balance_calc: не введено пластовое давление")
                return

            try:
                reservoir_pressure_mpa = float(txt_p.replace(",", "."))
            except ValueError:
                QMessageBox.warning(self, "Равновесие", "Некорректное значение давления.")
                logger.warning("run_balance_calc: некорректный ввод давления: %s", txt_p)
                return

            reservoir_pressure = reservoir_pressure_mpa * 1e6

            # Точки траектории
            pts = self._get_md_tvd_points()
            if not pts:
                QMessageBox.warning(
                    self,
                    "Равновесие",
                    "Не задана траектория (вкладка 'Траектория')."
                )
                logger.warning("run_balance_calc: нет данных по траектории")
                return

            max_md_traj = pts[-1][0]
            max_tvd_traj = pts[-1][1]

            # MD конструкции
            constr_md = self.construction_depth_md or 0.0

            # Выбор MD/TVD для расчёта
            if constr_md <= 0:
                # конструкции нет → используем максимум траектории
                used_md = max_md_traj
                used_tvd = max_tvd_traj
                logger.debug(
                    "run_balance_calc: глубина конструкции не задана, "
                    "используем максимальную TVD=%.2f м при MD=%.1f м",
                    used_tvd, used_md,
                )
            else:
                if constr_md > max_md_traj + 1e-6:
                    # конструкция глубже, чем траектория
                    QMessageBox.warning(
                        self,
                        "Равновесие",
                        (
                            "Глубина конструкции (MD = %.1f м) больше максимальной MD "
                            "по траектории (%.1f м).\n"
                            "Будет использована максимальная доступная TVD."
                        ) % (constr_md, max_md_traj)
                    )
                    used_md = max_md_traj
                    used_tvd = max_tvd_traj
                    logger.warning(
                        "run_balance_calc: MD конструкции=%.1f м > max_MD_траектории=%.1f м, "
                        "используем TVD по максимуму (%.2f м)",
                        constr_md, max_md_traj, used_tvd,
                    )
                else:
                    # нормальный случай: берём TVD на глубине конструкции
                    used_md = constr_md
                    used_tvd = self.get_tvd_for_md(constr_md)
                    logger.debug(
                        "run_balance_calc: используем TVD=%.2f м для MD конструкции=%.1f м "
                        "(max_MD_траектории=%.1f м)",
                        used_tvd, constr_md, max_md_traj,
                    )

            # Обновляем label TVD
            self.label_tvd.setText(f"TVD: {used_tvd:.2f} м (MD {used_md:.1f} м)")

            if used_tvd <= 0:
                QMessageBox.warning(
                    self,
                    "Равновесие",
                    "Не удалось определить TVD по траектории.\n"
                    "Проверьте данные во вкладке 'Траектория'."
                )
                logger.warning("run_balance_calc: used_tvd <= 0 (%.3f)", used_tvd)
                return

            # Жидкости
            if not self.fluids:
                QMessageBox.warning(self, "Равновесие", "Сначала добавьте жидкости на вкладке 'Жидкости'.")
                logger.warning("run_balance_calc: список fluids пуст")
                return

            i_t = self.combo_tubing.currentIndex()
            i_a = self.combo_annulus.currentIndex()
            if i_t < 0 or i_a < 0:
                QMessageBox.warning(self, "Равновесие", "Выберите жидкости в трубах и в затрубе.")
                logger.warning("run_balance_calc: не выбраны элементы в combo_tubing/combo_annulus")
                return

            if i_t >= len(self.fluids) or i_a >= len(self.fluids):
                QMessageBox.warning(self, "Равновесие", "Внутренняя ошибка при выборе жидкостей.")
                logger.error(
                    "run_balance_calc: индекс жидкости выходит за пределы: "
                    "i_t=%s, i_a=%s, len=%s", i_t, i_a, len(self.fluids)
                )
                return

            fluid_tubing = self.fluids[i_t]
            fluid_annulus = self.fluids[i_a]
            logger.debug(
                "run_balance_calc: tubing=%s (ρ=%.3f), annulus=%s (ρ=%.3f)",
                getattr(fluid_tubing, "name", "?"),
                getattr(fluid_tubing, "density", 0.0),
                getattr(fluid_annulus, "name", "?"),
                getattr(fluid_annulus, "density", 0.0),
            )

            # Расчёт равновесия. max_tvd_m = used_tvd → высоты не выйдут за предел TVD
            results, h_t, h_a, V_t, V_a = calculate_balance(
                reservoir_pressure,
                used_tvd,       # max_tvd_m
                fluid_tubing,
                fluid_annulus,
                # геометрию труб/ствола пока берём из дефолта balance_calc
            )

            logger.debug(
                "Результаты расчёта равновесия: h_t=%.2f, h_a=%.2f, V_t=%.3f, V_a=%.3f",
                h_t, h_a, V_t, V_a
            )
            self.label_balance.setText(render_balance_text(results))

            self.h_tubing = h_t
            self.h_annulus = h_a
            self.v_tubing = V_t
            self.v_annulus = V_a

            # Отрисовка столбов жидкости (по TVD, но в координатах MD сцены они 1:1)
            if self.scene is not None:
                self.scene.draw_fluids(
                    h_t_md=h_t,
                    h_a_md=h_a,
                    color_t=getattr(fluid_tubing, "color", None),
                    color_a=getattr(fluid_annulus, "color", None),
                )

        except Exception:
            logger.exception("Ошибка в run_balance_calc")
            QMessageBox.warning(
                self,
                "Ошибка расчёта равновесия",
                "Произошла непредвиденная ошибка.\nСм. лог для деталей."
            )

    # ---------- Работа со списком жидкостей ----------

    def populate_fluid_combos(self):
        """
        Обновляет содержимое комбобоксов на основе текущего списка fluids.
        """
        if not hasattr(self, "combo_tubing") or not hasattr(self, "combo_annulus"):
            logger.debug("populate_fluid_combos: combo_tubing/combo_annulus ещё не созданы")
            return

        self.combo_tubing.blockSignals(True)
        self.combo_annulus.blockSignals(True)

        self.combo_tubing.clear()
        self.combo_annulus.clear()

        if not self.fluids:
            self.combo_tubing.addItem("Нет жидкостей")
            self.combo_annulus.addItem("Нет жидкостей")
            logger.debug("populate_fluid_combos: fluids пуст, добавлены заглушки")
        else:
            names = [
                f"{f.name or 'Без названия'} — {f.density:.2f} г/см³"
                for f in self.fluids
            ]
            self.combo_tubing.addItems(names)
            self.combo_annulus.addItems(names)
            logger.debug("populate_fluid_combos: обновлено %s жидкостей", len(self.fluids))

        self.combo_tubing.blockSignals(False)
        self.combo_annulus.blockSignals(False)
