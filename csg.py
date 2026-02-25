# csg.py — главный модуль GUI Well Volume Calculator / PocketWell (десктоп)
# Версия: с кейс-менеджером (проект/месторождение/скважина/кейс), сохранением,
#         модулями "Объёмы / Равновесие / Отдувка / Индикаторная пачка",
#         и поддержкой цветов жидкостей (двойной клик по строке).

import os
import sys
import json
import shutil
import logging

# Ensure local imports work regardless of launch path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

CASES_ROOT = os.path.join(BASE_DIR, "cases")

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTableWidget, QTableWidgetItem, QLabel, QTabWidget, QStackedWidget,
    QPushButton, QToolBar, QMessageBox, QMenu, QSplitter, QGroupBox,
    QHeaderView, QAction, QDialog, QTreeWidget, QTreeWidgetItem,
    QFormLayout, QDialogButtonBox, QLineEdit, QInputDialog, QColorDialog
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QColor, QBrush

from logger_setup import setup_logger
from wellscene import WellScene, WellView
from bha import Casing, BHAElement
from volumes_calc import calculate_volumes
from fluids import render_fluid_summary
from trajectory_tab import TrajectoryTab
from balance_tab import BalanceTab
from displacement_tab import DisplacementTab
from indicator_pill_tab import IndicatorPillTab

from models_fluids import Fluid, fluid_color_by_index_for_type
from well_utils import (
    compute_casing_params,
    parse_float_cell,
    set_table_item,
    normalize_bha_name,
)

logger = logging.getLogger("WellApp.gui")


# ====================== Диалог выбора / управления кейсами ===================


class CaseManagerDialog(QDialog):
    """
    Окно управления кейсами:
    CASES_ROOT / Проект / Месторождение / Скважина / Кейс.json
    """

    def __init__(self, parent=None, current_case_path: str | None = None):
        super().__init__(parent)
        self.setWindowTitle("Проекты и кейсы")
        self.resize(700, 500)

        self.current_case_path = current_case_path
        self.selected_case_path: str | None = None

        main_layout = QHBoxLayout(self)

        # ------ Левая часть: дерево + кнопки ------
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Имя", "Тип"])
        self.tree.itemSelectionChanged.connect(self.on_tree_selection_changed)
        self.tree.itemDoubleClicked.connect(self.on_item_double_clicked)

        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addWidget(self.tree)

        btn_row = QHBoxLayout()
        self.btn_add_project = QPushButton("Добавить проект")
        self.btn_delete = QPushButton("Удалить")
        self.btn_add_project.clicked.connect(self.on_add_project)
        self.btn_delete.clicked.connect(self.on_delete_item)
        btn_row.addWidget(self.btn_add_project)
        btn_row.addWidget(self.btn_delete)
        left_layout.addLayout(btn_row)

        main_layout.addWidget(left_widget, 2)

        # ------ Правая часть: поля проекта / кейса ------
        right = QWidget()
        form_layout = QFormLayout(right)

        self.edit_project = QLineEdit()
        self.edit_field = QLineEdit()
        self.edit_well = QLineEdit()
        self.edit_case = QLineEdit()

        form_layout.addRow("Проект:", self.edit_project)
        form_layout.addRow("Месторождение:", self.edit_field)
        form_layout.addRow("Скважина:", self.edit_well)
        form_layout.addRow("Кейс:", self.edit_case)

        self.info_label = QLabel(
            "Выберите существующий кейс слева\n"
            "или введите новые имена для создания нового."
        )
        self.info_label.setWordWrap(True)
        form_layout.addRow(self.info_label)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel, parent=self
        )
        self.buttons.accepted.connect(self.on_accept)
        self.buttons.rejected.connect(self.reject)
        form_layout.addRow(self.buttons)

        main_layout.addWidget(right, 3)

        self.populate_tree()
        self.preselect_current()

    # ---------- построение дерева ----------

    def populate_tree(self):
        self.tree.clear()
        if not os.path.isdir(CASES_ROOT):
            return

        for proj in sorted(os.listdir(CASES_ROOT)):
            proj_dir = os.path.join(CASES_ROOT, proj)
            if not os.path.isdir(proj_dir):
                continue
            proj_item = QTreeWidgetItem([proj, "проект"])
            self.tree.addTopLevelItem(proj_item)

            for field in sorted(os.listdir(proj_dir)):
                field_dir = os.path.join(proj_dir, field)
                if not os.path.isdir(field_dir):
                    continue
                field_item = QTreeWidgetItem([field, "месторождение"])
                proj_item.addChild(field_item)

                for well in sorted(os.listdir(field_dir)):
                    well_dir = os.path.join(field_dir, well)
                    if not os.path.isdir(well_dir):
                        continue
                    well_item = QTreeWidgetItem([well, "скважина"])
                    field_item.addChild(well_item)

                    for fname in sorted(os.listdir(well_dir)):
                        if not fname.lower().endswith(".json"):
                            continue
                        case_name = os.path.splitext(fname)[0]
                        case_item = QTreeWidgetItem([case_name, "кейс"])
                        case_item.setData(0, Qt.UserRole, os.path.join(well_dir, fname))
                        well_item.addChild(case_item)

        self.tree.expandAll()

    def preselect_current(self):
        """Подсветить в дереве текущий кейс (если есть)."""
        if not self.current_case_path:
            return

        path_norm = os.path.normpath(self.current_case_path)

        def walk(item: QTreeWidgetItem):
            for i in range(item.childCount()):
                ch = item.child(i)
                p = ch.data(0, Qt.UserRole)
                if isinstance(p, str) and os.path.normpath(p) == path_norm:
                    self.tree.setCurrentItem(ch)
                    self.on_tree_selection_changed()
                    return True
                if walk(ch):
                    return True
            return False

        for i in range(self.tree.topLevelItemCount()):
            if walk(self.tree.topLevelItem(i)):
                break

    # ---------- обработчики дерева ----------

    def on_tree_selection_changed(self):
        item = self.tree.currentItem()
        if not item:
            return

        names = []
        node = item
        while node is not None:
            names.append(node.text(0))
            node = node.parent()
        names.reverse()  # [proj, field, well, case?]

        proj = names[0] if len(names) >= 1 else ""
        field = names[1] if len(names) >= 2 else ""
        well = names[2] if len(names) >= 3 else ""
        case = names[3] if len(names) >= 4 else ""

        self.edit_project.setText(proj)
        self.edit_field.setText(field)
        self.edit_well.setText(well)
        if item.text(1) == "кейс":
            self.edit_case.setText(case)

    def on_item_double_clicked(self, item, column):
        if item.text(1) == "кейс":
            self.on_accept()

    # ---------- добавление / удаление ----------

    def on_add_project(self):
        """Кнопка 'Добавить проект' — создаёт новый каталог-проект."""
        name, ok = QInputDialog.getText(self, "Новый проект", "Имя проекта:")
        if not ok:
            return
        name = (name or "").strip()
        if not name:
            return

        path = os.path.join(CASES_ROOT, name)
        if os.path.exists(path):
            QMessageBox.warning(self, "Проект", f"Проект '{name}' уже существует.")
            return

        os.makedirs(path, exist_ok=True)
        self.populate_tree()

        for i in range(self.tree.topLevelItemCount()):
            it = self.tree.topLevelItem(i)
            if it.text(0) == name:
                self.tree.setCurrentItem(it)
                break

        self.edit_project.setText(name)
        self.edit_field.clear()
        self.edit_well.clear()
        self.edit_case.clear()

    def on_delete_item(self):
        """Кнопка 'Удалить' — удаляет выбранный проект/ветку/кейс из файловой системы."""
        item = self.tree.currentItem()
        if not item:
            return

        typ = item.text(1)
        name = item.text(0)
        path = None

        if typ == "проект":
            path = os.path.join(CASES_ROOT, name)
        elif typ == "месторождение":
            proj_item = item.parent()
            if proj_item:
                path = os.path.join(CASES_ROOT, proj_item.text(0), name)
        elif typ == "скважина":
            field_item = item.parent()
            proj_item = field_item.parent() if field_item else None
            if proj_item and field_item:
                path = os.path.join(CASES_ROOT, proj_item.text(0), field_item.text(0), name)
        elif typ == "кейс":
            path = item.data(0, Qt.UserRole)

        if not path:
            return

        path_norm = os.path.normpath(path)
        root_norm = os.path.normpath(CASES_ROOT)

        # защита от удаления корня
        if path_norm == root_norm:
            QMessageBox.warning(self, "Удаление", "Нельзя удалить корневой каталог проектов.")
            return

        # защита от удаления вне CASES_ROOT
        if not os.path.commonpath([root_norm, path_norm]) == root_norm:
            QMessageBox.warning(self, "Удаление", "Невозможно удалить: путь вне каталога проектов.")
            return

        if not os.path.exists(path):
            self.populate_tree()
            return

        msg = f"Удалить {typ} '{name}'?\nЭто действие нельзя отменить."
        if QMessageBox.question(self, "Удаление", msg, QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
            return

        try:
            if os.path.isdir(path):
                shutil.rmtree(path)
            else:
                os.remove(path)
        except Exception as e:
            QMessageBox.warning(self, "Удаление", f"Ошибка при удалении:\n{e}")
            return

        self.populate_tree()
        self.edit_project.clear()
        self.edit_field.clear()
        self.edit_well.clear()
        self.edit_case.clear()

    # ---------- подтверждение выбора / создание нового кейса ----------

    def on_accept(self):
        proj = (self.edit_project.text() or "").strip()
        field = (self.edit_field.text() or "").strip()
        well = (self.edit_well.text() or "").strip()
        case = (self.edit_case.text() or "").strip()

        if not (proj and field and well and case):
            QMessageBox.warning(self, "Кейс", "Нужно заполнить Проект, Месторождение, Скважину и Кейс.")
            return

        dir_path = os.path.join(CASES_ROOT, proj, field, well)
        os.makedirs(dir_path, exist_ok=True)
        self.selected_case_path = os.path.join(dir_path, case + ".json")
        self.accept()


# =============================== Главное окно ===============================


class WellApp(QMainWindow):
    def __init__(self):
        super().__init__()
        logger.debug("Инициализация WellApp")

        os.makedirs(CASES_ROOT, exist_ok=True)

        self.setWindowTitle("Well Volume Calculator")
        self.setGeometry(200, 200, 1400, 800)

        # --- данные (общие для вкладок) ---
        self.casings = []
        self.bha = []
        self.fluids = []  # общий список Fluid, один экземпляр на всё приложение
        self.current_case_path: str | None = None

        # ---------- Правая панель: сцена / вид ----------
        self.scene = WellScene()
        self.view = WellView(self.scene)

        # ---------- Левые вкладки (настройки) ----------
        self.tab_trajectory = TrajectoryTab()
        self.tab_construction = QWidget()
        self.tab_bha = QWidget()
        self.tab_fluids = QWidget()
        QVBoxLayout(self.tab_fluids)

        self.settings_tabs = QTabWidget()
        self.settings_tabs.setTabPosition(QTabWidget.West)
        self.settings_tabs.setTabShape(QTabWidget.Triangular)

        self.settings_tabs.addTab(self.tab_trajectory, "Траектория")
        self.settings_tabs.addTab(self.tab_construction, "Конструкция")
        self.settings_tabs.addTab(self.tab_bha, "КНБК")
        self.settings_tabs.addTab(self.tab_fluids, "Жидкости")

        # ---------- Центральные вкладки (расчёты) ----------
        self.tab_volumes = QWidget()

        # Равновесие
        self.tab_balance = BalanceTab(
            parent=None,
            fluids=self.fluids,
            trajectory_tab=self.tab_trajectory,
            scene=self.scene,
        )
        self.tab_balance.construction_depth_md = 0.0

        # Отдувка
        self.tab_displacement = DisplacementTab(
            parent=None,
            fluids=self.fluids,
            trajectory_tab=self.tab_trajectory,
            scene=self.scene,
        )
        self.tab_displacement.construction_depth_md = 0.0

        # Индикаторная пачка (НОВЫЕ колбэки под несколько OH + учёт обсадки/внутр.объёма)
        self.tab_indicator_pill = IndicatorPillTab(
            parent=None,
            get_openhole_intervals_cb=self.get_openhole_intervals,
            get_geometry_cb=self.get_indicator_geometry,
            apply_openhole_id_cb=self.apply_openhole_eff_id,
        )

        # связь траектории с модулями (автообновление TVD-лейблов)
        self.tab_trajectory.balance_tab = self.tab_balance
        self.tab_trajectory.displacement_tab = self.tab_displacement

        self.central_stack = QStackedWidget()
        self.central_stack.addWidget(self.tab_volumes)        # 0 — Объёмы
        self.central_stack.addWidget(self.tab_balance)        # 1 — Равновесие
        self.central_stack.addWidget(self.tab_displacement)   # 2 — Отдувка
        self.central_stack.addWidget(self.tab_indicator_pill) # 3 — Индикаторная пачка
        self.central_stack.currentChanged.connect(self.on_stack_changed)

        # ---------- Основной сплиттер ----------
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self.settings_tabs)
        self.settings_tabs.setMinimumWidth(400)
        splitter.addWidget(self.central_stack)
        splitter.addWidget(self.view)
        self.view.setMinimumWidth(500)
        splitter.setSizes([400, 800, 500])
        self.setCentralWidget(splitter)

        # ---------- Верхняя панель: настройки (сохранить / проекты) ----------
        self.settings_toolbar = QToolBar("Настройки")
        self.addToolBar(Qt.TopToolBarArea, self.settings_toolbar)
        self.settings_toolbar.setMovable(False)

        act_save = QAction("💾 Сохранить", self)
        act_save.triggered.connect(self.save_current_case)
        self.settings_toolbar.addAction(act_save)

        act_cases = QAction("📁 Проекты…", self)
        act_cases.triggered.connect(self.open_case_manager)
        self.settings_toolbar.addAction(act_cases)

        # ---------- Вторая строка: выбор модуля ----------
        self.addToolBarBreak(Qt.TopToolBarArea)
        self.modules_toolbar = QToolBar("Модули")
        self.modules_toolbar.setMovable(False)
        self.addToolBar(Qt.TopToolBarArea, self.modules_toolbar)

        self.modules_toolbar.addAction("Объёмы", lambda: self.central_stack.setCurrentIndex(0))
        self.modules_toolbar.addAction("Равновесие", lambda: self.central_stack.setCurrentIndex(1))
        self.modules_toolbar.addAction("Отдувка", lambda: self.central_stack.setCurrentIndex(2))
        self.modules_toolbar.addAction("Инд. пачка", lambda: self.central_stack.setCurrentIndex(3))

        # Инициализация вкладок слева и "Объёмы"
        self.init_fluids_tab()
        self.init_construction_tab()
        self.init_bha_tab()
        self.init_volumes_tab()

    # ===================== Служебное: очистка / новый кейс =====================

    def new_case(self):
        """
        Очистить все таблицы и подготовить "пустой" кейс.
        Используется при создании нового кейса (файл ещё не существует).
        """
        logger.debug("Создание нового пустого кейса (new_case)")

        # траектория
        t = self.tab_trajectory
        t.table.blockSignals(True)
        t.table.setRowCount(0)
        t.altitude_edit.setText("0.0")
        t.azimcorr_edit.setText("0.0")
        t.table.blockSignals(False)
        t.add_row()  # добавит одну точку и пересчитает TVD

        # конструкция
        self.table_casing.setRowCount(0)
        self.table_openhole.setRowCount(0)
        self.add_casing_row()

        # КНБК
        self.table_bha.setRowCount(0)
        self.add_bha_row()
        set_table_item(self.table_bha, 0, 0, "УБТ")
        set_table_item(self.table_bha, 0, 1, "10.0")
        set_table_item(self.table_bha, 0, 2, "203.2")
        set_table_item(self.table_bha, 0, 3, "70.0")

        # жидкости
        self.clear_fluids()
        self.add_fluid_row("Раствор")

        # результаты/сцена
        self.label_results.setText("Результаты будут здесь")
        self.casings.clear()
        self.bha.clear()
        self.scene.clear()

        # обнулить глубины в модулях
        self.tab_balance.construction_depth_md = 0.0
        self.tab_displacement.construction_depth_md = 0.0

        # обновим список OH в инд.пачке
        try:
            self.tab_indicator_pill.refresh_openhole_list()
        except Exception:
            pass

    # ========================= Кейсы / сохранение =========================

    def open_case_manager(self):
        dlg = CaseManagerDialog(self, current_case_path=self.current_case_path)
        if dlg.exec_() == QDialog.Accepted and dlg.selected_case_path:
            self.current_case_path = dlg.selected_case_path
            logger.info("Выбран кейс: %s", self.current_case_path)

            if os.path.isfile(self.current_case_path):
                self.load_case_from_file(self.current_case_path)
            else:
                self.new_case()

    def save_current_case(self):
        """
        Сохранить текущие данные в файл.
        Если кейс ещё не выбран — открываем диалог и спрашиваем, куда сохранить.
        """
        if not self.current_case_path:
            dlg = CaseManagerDialog(self, current_case_path=None)
            if dlg.exec_() != QDialog.Accepted or not dlg.selected_case_path:
                return
            self.current_case_path = dlg.selected_case_path

        try:
            self.save_case_to_file(self.current_case_path)
            QMessageBox.information(self, "Сохранение", f"Кейс сохранён:\n{self.current_case_path}")
        except Exception:
            logger.exception("Ошибка при сохранении кейса")
            QMessageBox.warning(self, "Сохранение", "Ошибка при сохранении кейса, см. лог.")

    def save_case_to_file(self, path: str):
        """
        Сериализует таблицы/жидкости в JSON.
        """
        logger.debug("Сохранение кейса в %s", path)

        # сначала синхронизируем fluids с таблицей (включая цвета)
        self.collect_fluids()

        data = {}

        # --- траектория ---
        tr = {
            "altitude": self.tab_trajectory.altitude_edit.text(),
            "azimcorr": self.tab_trajectory.azimcorr_edit.text(),
            "rows": [],
        }
        table = self.tab_trajectory.table
        for r in range(table.rowCount()):
            row_vals = []
            for c in range(3):  # MD, угол, азимут (TVD пересчитается)
                item = table.item(r, c)
                row_vals.append(item.text() if item else "")
            tr["rows"].append(row_vals)
        data["trajectory"] = tr

        # --- конструкция ---
        constr = {"casing": [], "openhole": []}
        for table_obj, key, cols in (
            (self.table_casing, "casing", 6),
            (self.table_openhole, "openhole", 4),
        ):
            for r in range(table_obj.rowCount()):
                row_vals = []
                for c in range(cols):
                    item = table_obj.item(r, c)
                    row_vals.append(item.text() if item else "")
                constr[key].append(row_vals)
        data["construction"] = constr

        # --- КНБК ---
        bha_data = {"rows": []}
        for r in range(self.table_bha.rowCount()):
            row_vals = []
            for c in range(4):
                item = self.table_bha.item(r, c)
                row_vals.append(item.text() if item else "")
            bha_data["rows"].append(row_vals)
        data["bha"] = bha_data

        # --- жидкости ---
        fluids_list = []
        for idx, f in enumerate(self.fluids):
            color = getattr(f, "color", None)
            if isinstance(color, QColor):
                col = [color.red(), color.green(), color.blue(), color.alpha()]
            else:
                col = None
            fluids_list.append(
                {
                    "name": f.name,
                    "type": f.type,
                    "density": float(f.density),
                    "comment": getattr(f, "comment", ""),
                    "color": col,
                }
            )
        data["fluids"] = fluids_list

        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        logger.debug("Кейс успешно сохранён")

    def load_case_from_file(self, path: str):
        """
        Загружает данные из JSON в таблицы.
        Никаких расчётов / compute_casing_params здесь НЕ вызываем.
        """
        logger.debug("Загрузка кейса из %s", path)
        if not os.path.isfile(path):
            logger.info("Файл кейса не найден, создаём пустой кейс")
            self.new_case()
            return

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # --- траектория ---
        tr = data.get("trajectory", {})
        table = self.tab_trajectory.table
        table.blockSignals(True)
        table.setRowCount(0)

        self.tab_trajectory.altitude_edit.setText(tr.get("altitude", "0.0"))
        self.tab_trajectory.azimcorr_edit.setText(tr.get("azimcorr", "0.0"))

        for row_vals in tr.get("rows", []):
            r = table.rowCount()
            table.insertRow(r)
            for c in range(3):
                txt = row_vals[c] if c < len(row_vals) else ""
                table.setItem(r, 0 + c, QTableWidgetItem(str(txt)))
            table.setItem(r, 3, QTableWidgetItem(""))  # TVD посчитается
        table.blockSignals(False)
        self.tab_trajectory.update_tvd()

        # --- конструкция ---
        constr = data.get("construction", {})
        self.table_casing.setRowCount(0)
        for row_vals in constr.get("casing", []):
            r = self.table_casing.rowCount()
            self.table_casing.insertRow(r)
            for c in range(6):
                txt = row_vals[c] if c < len(row_vals) else ""
                self.table_casing.setItem(r, c, QTableWidgetItem(str(txt)))

        self.table_openhole.setRowCount(0)
        for row_vals in constr.get("openhole", []):
            r = self.table_openhole.rowCount()
            self.table_openhole.insertRow(r)
            for c in range(4):
                txt = row_vals[c] if c < len(row_vals) else ""
                self.table_openhole.setItem(r, c, QTableWidgetItem(str(txt)))

        # --- КНБК ---
        bha_data = data.get("bha", {})
        self.table_bha.setRowCount(0)
        for row_vals in bha_data.get("rows", []):
            r = self.table_bha.rowCount()
            self.table_bha.insertRow(r)
            for c in range(4):
                txt = row_vals[c] if c < len(row_vals) else ""
                self.table_bha.setItem(r, c, QTableWidgetItem(str(txt)))

        # --- жидкости ---
        fluids_data = data.get("fluids", [])
        self.table_fluids.blockSignals(True)
        self.table_fluids.setRowCount(0)
        self.fluids.clear()

        for idx, fd in enumerate(fluids_data):
            name = fd.get("name", f"Жидкость {idx + 1}")
            density = float(fd.get("density", 1.2))
            ftype = fd.get("type", name.split()[0] if name else "Жидкость")

            col_list = fd.get("color")
            if col_list and len(col_list) >= 3:
                color = QColor(*col_list)
            else:
                color = fluid_color_by_index_for_type(ftype, idx)

            r = self.table_fluids.rowCount()
            self.table_fluids.insertRow(r)
            self.table_fluids.setItem(r, 0, QTableWidgetItem(name))
            self.table_fluids.setItem(r, 1, QTableWidgetItem(f"{density:.2f}"))
            self.table_fluids.setItem(r, 2, QTableWidgetItem(""))

            for c in range(self.table_fluids.columnCount()):
                it = self.table_fluids.item(r, c)
                if it:
                    it.setBackground(QBrush(color))

            self.fluids.append(
                Fluid(name=name, type=ftype, density=density, comment="", color=color)
            )

        self.table_fluids.blockSignals(False)

        if self.tab_balance:
            self.tab_balance.populate_fluid_combos()
        if self.tab_displacement:
            self.tab_displacement.populate_fluid_combo()

        # после загрузки обновим глубину конструкции и картинку
        self.calculate_and_plot()

        # обновим список OH в инд.пачке
        try:
            self.tab_indicator_pill.refresh_openhole_list()
        except Exception:
            pass

    # ==================== Реакция на переключение модулей ====================

    def on_stack_changed(self, index: int):
        if index == 0:
            return
        elif index == 1:
            logger.debug("Переключение на вкладку 'Равновесие'")
            self.tab_balance.populate_fluid_combos()
            self.tab_balance.update_tvd_display()
        elif index == 2:
            logger.debug("Переключение на вкладку 'Отдувка'")
            self.tab_displacement.populate_fluid_combo()
            self.tab_displacement.update_tvd_display()
        elif index == 3:
            logger.debug("Переключение на вкладку 'Индикаторная пачка'")
            try:
                self.tab_indicator_pill.refresh_openhole_list()
            except Exception:
                pass

    # ================== Общие действия (удаление строк и т.п.) ==================

    def delete_selected_rows(self, table):
        rows = sorted({i.row() for i in table.selectedIndexes()}, reverse=True)
        for r in rows:
            table.removeRow(r)
        logger.debug("Удалено строк: %s из таблицы %s", len(rows), table.objectName() or table)

    def keyPressEvent(self, event):
        fw = QApplication.focusWidget()
        tables = (
            getattr(self, "table_casing", None),
            getattr(self, "table_bha", None),
            getattr(self, "table_fluids", None),
            getattr(self, "table_openhole", None),
        )
        if event.key() == Qt.Key_Delete and fw in tables:
            self.delete_selected_rows(fw)
            event.accept()
        else:
            super().keyPressEvent(event)

    def contextMenuEvent(self, event):
        fw = QApplication.focusWidget()
        tables = (
            getattr(self, "table_casing", None),
            getattr(self, "table_bha", None),
            getattr(self, "table_fluids", None),
            getattr(self, "table_openhole", None),
        )
        if fw in tables:
            menu = QMenu(self)
            action = menu.addAction("Удалить")
            if menu.exec_(self.mapToGlobal(event.pos())) == action:
                self.delete_selected_rows(fw)
        else:
            super().contextMenuEvent(event)

    # ============================ Конструкция ============================

    def init_construction_tab(self):
        logger.debug("Инициализация вкладки 'Конструкция'")
        layout = QVBoxLayout(self.tab_construction)

        # --- Верхняя часть: Колонны ---
        group_casing = QGroupBox("Колонны")
        layout_casing = QVBoxLayout(group_casing)

        self.table_casing = QTableWidget(0, 6)
        self.table_casing.setHorizontalHeaderLabels(
            ["Тип", "OD (мм)", "ID", "Толщина (мм)", "Длина (м)", "Глубина (м)"]
        )
        self.table_casing.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table_casing.verticalHeader().setVisible(False)
        self.table_casing.setAlternatingRowColors(True)
        self.table_casing.setSelectionBehavior(QTableWidget.SelectRows)
        layout_casing.addWidget(self.table_casing)

        btns_casing = QHBoxLayout()
        btns_casing.addWidget(QPushButton("Добавить колонну", clicked=self.add_casing_row))
        btns_casing.addWidget(QPushButton("Очистить", clicked=lambda: self.table_casing.setRowCount(0)))
        layout_casing.addLayout(btns_casing)
        layout.addWidget(group_casing)

        # --- Нижняя часть: Открытый ствол ---
        group_openhole = QGroupBox("Открытый ствол")
        layout_openhole = QVBoxLayout(group_openhole)

        self.table_openhole = QTableWidget(0, 4)
        self.table_openhole.setHorizontalHeaderLabels(
            ["Тип", "Эфф. ID", "Длина (м)", "Глубина (м)"]
        )
        self.table_openhole.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table_openhole.verticalHeader().setVisible(False)
        self.table_openhole.setAlternatingRowColors(True)
        self.table_openhole.setSelectionBehavior(QTableWidget.SelectRows)
        layout_openhole.addWidget(self.table_openhole)

        btns_openhole = QHBoxLayout()
        btns_openhole.addWidget(QPushButton("Добавить Open Hole", clicked=self.add_openhole_row))
        btns_openhole.addWidget(QPushButton("Очистить", clicked=lambda: self.table_openhole.setRowCount(0)))
        layout_openhole.addLayout(btns_openhole)
        layout.addWidget(group_openhole)

        self.add_casing_row()

    def add_casing_row(self):
        r = self.table_casing.rowCount()
        self.table_casing.insertRow(r)
        for i, val in enumerate(["Casing", "", "", "", "", ""]):
            self.table_casing.setItem(r, i, QTableWidgetItem(val))
        logger.debug("Добавлена строка колонны, всего строк: %s", self.table_casing.rowCount())

    def add_openhole_row(self):
        r = self.table_openhole.rowCount()
        self.table_openhole.insertRow(r)
        for i in range(4):
            self.table_openhole.setItem(r, i, QTableWidgetItem(""))
        set_table_item(self.table_openhole, r, 0, "Open Hole")
        logger.debug("Добавлена строка Open Hole, всего строк: %s", self.table_openhole.rowCount())

    # =============================== КНБК ===============================

    def init_bha_tab(self):
        logger.debug("Инициализация вкладки 'КНБК'")
        layout = QVBoxLayout(self.tab_bha)
        self.table_bha = QTableWidget(0, 4)
        self.table_bha.setHorizontalHeaderLabels(["Элемент", "Длина (м)", "OD (мм)", "ID (мм)"])
        self.table_bha.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.table_bha)

        btns = QHBoxLayout()
        btn_add = QPushButton("Добавить элемент")
        btn_add.clicked.connect(self.add_bha_row)
        btn_paste = QPushButton("Вставить из буфера (WellPlan/Excel)")
        btn_paste.clicked.connect(self.paste_bha_from_clipboard)
        btn_clear = QPushButton("Очистить")
        btn_clear.clicked.connect(lambda: self.table_bha.setRowCount(0))
        btns.addWidget(btn_add)
        btns.addWidget(btn_paste)
        btns.addWidget(btn_clear)
        layout.addLayout(btns)

        self.add_bha_row()
        set_table_item(self.table_bha, 0, 0, "УБТ")
        set_table_item(self.table_bha, 0, 1, "10.0")
        set_table_item(self.table_bha, 0, 2, "203.2")
        set_table_item(self.table_bha, 0, 3, "70.0")

    def add_bha_row(self):
        row = self.table_bha.rowCount()
        self.table_bha.insertRow(row)
        for i in range(4):
            self.table_bha.setItem(row, i, QTableWidgetItem(""))
        logger.debug("Добавлена строка КНБК, всего строк: %s", self.table_bha.rowCount())

    def paste_bha_from_clipboard(self):
        text = QApplication.clipboard().text()
        if not text.strip():
            QMessageBox.warning(self, "Вставка", "Буфер обмена пуст.")
            return

        lines = text.strip().splitlines()
        added = 0

        for raw_line in lines:
            line = raw_line.replace("\u00A0", "").strip()
            if not line:
                continue

            parts = [p.strip() for p in line.split("\t")]
            logger.debug("paste_bha_from_clipboard: сырая строка=%r, parts=%r", line, parts)

            if len(parts) < 3:
                logger.debug("Строка КНБК пропущена (мало колонок): %r", line)
                continue

            try:
                name_raw = parts[0]
                length_txt = parts[1]

                if len(parts) >= 4:
                    od_txt = parts[-2]
                    id_txt = parts[-1]
                else:
                    od_txt = parts[2]
                    id_txt = "0"

                length = float(length_txt.replace(",", "."))
                od = float(od_txt.replace(",", "."))
                id_ = float(id_txt.replace(",", "."))

                name = normalize_bha_name(name_raw)

            except Exception as e:
                logger.debug("Не удалось распарсить строку КНБК %r: %s", line, e)
                continue

            row = self.table_bha.rowCount()
            self.table_bha.insertRow(row)
            self.table_bha.setItem(row, 0, QTableWidgetItem(name))
            self.table_bha.setItem(row, 1, QTableWidgetItem(f"{length:.3f}"))
            self.table_bha.setItem(row, 2, QTableWidgetItem(f"{od:.1f}"))
            self.table_bha.setItem(row, 3, QTableWidgetItem(f"{id_:.1f}"))
            added += 1

        logger.debug("Из буфера вставлено элементов КНБК: %s", added)

    # ============================== Жидкости ==============================

    def init_fluids_tab(self):
        logger.debug("Инициализация вкладки 'Жидкости'")
        try:
            layout = self.tab_fluids.layout()
            if layout is None:
                layout = QVBoxLayout(self.tab_fluids)

            self.table_fluids = QTableWidget(0, 3)
            self.table_fluids.setHorizontalHeaderLabels(["Название", "Плотность, г/см³", "Цвет"])
            self.table_fluids.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
            self.table_fluids.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
            self.table_fluids.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
            layout.addWidget(self.table_fluids)

            btns = QHBoxLayout()
            btn_add_sol = QPushButton("Добавить раствор")
            btn_add_sol.clicked.connect(lambda: self.add_fluid_row("Раствор"))
            btn_add_buf = QPushButton("Добавить буфер")
            btn_add_buf.clicked.connect(lambda: self.add_fluid_row("Буфер"))
            btn_add_cem = QPushButton("Добавить цемент")
            btn_add_cem.clicked.connect(lambda: self.add_fluid_row("Цемент"))
            btn_clear = QPushButton("Очистить")
            btn_clear.clicked.connect(self.clear_fluids)
            for btn in (btn_add_sol, btn_add_buf, btn_add_cem, btn_clear):
                btns.addWidget(btn)
            layout.addLayout(btns)

            # первая строка
            self.table_fluids.blockSignals(True)
            self.add_fluid_row("Раствор")
            self.table_fluids.blockSignals(False)

            if self.tab_balance:
                self.tab_balance.populate_fluid_combos()
            if self.tab_displacement:
                self.tab_displacement.populate_fluid_combo()

            self.table_fluids.cellChanged.connect(self.on_fluid_table_changed)
            self.table_fluids.cellDoubleClicked.connect(self.on_fluid_cell_double_clicked)

        except Exception:
            logger.exception("Ошибка в init_fluids_tab")

    def add_fluid_row(self, fluid_type: str):
        try:
            row = self.table_fluids.rowCount()
            self.table_fluids.blockSignals(True)
            self.table_fluids.insertRow(row)

            name = f"{fluid_type} {row + 1}"
            density = 1.20
            color = fluid_color_by_index_for_type(fluid_type, row) or QColor(240, 240, 240)

            self.table_fluids.setItem(row, 0, QTableWidgetItem(name))
            self.table_fluids.setItem(row, 1, QTableWidgetItem(f"{density:.2f}"))
            self.table_fluids.setItem(row, 2, QTableWidgetItem(""))
            self.table_fluids.blockSignals(False)

            for col in range(self.table_fluids.columnCount()):
                it = self.table_fluids.item(row, col)
                if it:
                    it.setBackground(QBrush(color))

            self.fluids.append(
                Fluid(name=name, type=fluid_type, density=density, comment="", color=color)
            )

            if self.tab_balance:
                self.tab_balance.populate_fluid_combos()
            if self.tab_displacement:
                self.tab_displacement.populate_fluid_combo()

            logger.debug("Добавлена жидкость: %s, %s г/см³, тип %s", name, density, fluid_type)

        except Exception:
            logger.exception("[add_fluid_row] Ошибка")

    def collect_fluids(self):
        self.fluids.clear()
        for row in range(self.table_fluids.rowCount()):
            try:
                name_item = self.table_fluids.item(row, 0)
                dens_item = self.table_fluids.item(row, 1)
                if not name_item or not dens_item:
                    continue

                name = name_item.text()
                density = float(dens_item.text().replace(",", "."))
                fluid_type = name.split()[0] if name else "Жидкость"

                color = None
                bg = name_item.background()
                if isinstance(bg, QBrush):
                    color = bg.color()
                if not isinstance(color, QColor) or not color.isValid():
                    color = fluid_color_by_index_for_type(fluid_type, row)

                self.fluids.append(Fluid(name, fluid_type, density, "", color))
            except Exception:
                logger.exception("Ошибка при создании Fluid")
                continue

        logger.debug("Итоговое содержимое fluids: %s", [f.name for f in self.fluids])

    def on_fluid_table_changed(self, row, column):
        QTimer.singleShot(0, lambda: self._process_fluid_change(row, column))

    def _process_fluid_change(self, row, column):
        try:
            if not self.fluids or row < 0 or row >= len(self.fluids):
                return

            item = self.table_fluids.item(row, column)
            if not item:
                return

            if column == 1:  # плотность
                txt = item.text() or ""
                if not txt.strip():
                    return
                try:
                    density = float(txt.replace(",", "."))
                    item.setBackground(QBrush(Qt.white))
                except Exception:
                    density = 1.0
                    item.setBackground(QBrush(Qt.red))
                self.fluids[row].density = density

            elif column == 0:  # название
                name = item.text() or ""
                fluid_type = name.split()[0] if name else "Жидкость"
                self.fluids[row].name = name
                self.fluids[row].type = fluid_type

                color = self.fluids[row].color
                if not isinstance(color, QColor) or not color.isValid():
                    color = fluid_color_by_index_for_type(fluid_type, row)
                    self.fluids[row].color = color

                for c in range(self.table_fluids.columnCount()):
                    it = self.table_fluids.item(row, c)
                    if it:
                        it.setBackground(QBrush(color))

            if self.tab_balance:
                self.tab_balance.populate_fluid_combos()
            if self.tab_displacement:
                self.tab_displacement.populate_fluid_combo()

        except Exception:
            logger.exception("[process_fluid_change] Ошибка")

    def on_fluid_cell_double_clicked(self, row: int, column: int):
        try:
            if row < 0 or row >= len(self.fluids):
                return

            current_color = self.fluids[row].color
            if not isinstance(current_color, QColor) or not current_color.isValid():
                current_color = QColor(240, 240, 240)

            new_color = QColorDialog.getColor(current_color, self, "Выберите цвет жидкости")
            if not new_color.isValid():
                return

            self.fluids[row].color = new_color

            for c in range(self.table_fluids.columnCount()):
                it = self.table_fluids.item(row, c)
                if it is None:
                    it = QTableWidgetItem("")
                    self.table_fluids.setItem(row, c, it)
                it.setBackground(QBrush(new_color))

            if self.tab_balance:
                self.tab_balance.populate_fluid_combos()
            if self.tab_displacement:
                self.tab_displacement.populate_fluid_combo()

        except Exception:
            logger.exception("on_fluid_cell_double_clicked: ошибка")

    def clear_fluids(self):
        try:
            self.table_fluids.blockSignals(True)
            self.table_fluids.setRowCount(0)
            self.table_fluids.blockSignals(False)
            self.fluids.clear()

            if self.tab_balance:
                self.tab_balance.populate_fluid_combos()
            if self.tab_displacement:
                self.tab_displacement.populate_fluid_combo()

            logger.debug("Список жидкостей очищен")
        except Exception:
            logger.exception("[clear_fluids] Ошибка")

    # =========================== Объёмы / схема ===========================

    def init_volumes_tab(self):
        logger.debug("Инициализация вкладки 'Объёмы'")
        layout = QVBoxLayout()
        self.btn_calc = QPushButton("Рассчитать и построить схему")
        self.btn_calc.clicked.connect(self.calculate_and_plot)
        layout.addWidget(self.btn_calc)

        self.label_results = QLabel("Результаты будут здесь")
        self.label_results.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.label_results.setMinimumHeight(120)
        layout.addWidget(self.label_results)

        self.tab_volumes.setLayout(layout)

    def calculate_and_plot(self):
        logger.debug("Старт расчёта объёмов и построения схемы")
        try:
            self.casings.clear()
            rows = []

            # Колонны
            for r in range(self.table_casing.rowCount()):
                typ = self.table_casing.item(r, 0).text() if self.table_casing.item(r, 0) else "Casing"
                name = typ
                od = parse_float_cell(self.table_casing.item(r, 1))
                id_ = parse_float_cell(self.table_casing.item(r, 2))
                wall = parse_float_cell(self.table_casing.item(r, 3))
                length_in = parse_float_cell(self.table_casing.item(r, 4))
                depth_in = parse_float_cell(self.table_casing.item(r, 5))
                rows.append((typ, name, od, id_, wall, length_in, depth_in, r, "casing"))

            # Открытый ствол
            for r in range(self.table_openhole.rowCount()):
                typ = self.table_openhole.item(r, 0).text() if self.table_openhole.item(r, 0) else "Open Hole"
                name = typ
                id_ = parse_float_cell(self.table_openhole.item(r, 1))
                od = None
                wall = 0.0
                length_in = parse_float_cell(self.table_openhole.item(r, 2))
                depth_in = parse_float_cell(self.table_openhole.item(r, 3))
                rows.append((typ, name, od, id_, wall, length_in, depth_in, r, "openhole"))

            # Расчёт длины/глубины последовательно
            prev_depth = 0.0
            for idx, (typ, name, od, id_, wall, length_in, depth_in, r, source) in enumerate(rows):
                if idx == 0:
                    depth = depth_in or length_in or 0.0
                    length = depth
                else:
                    if depth_in is not None and length_in is None:
                        depth = depth_in
                        length = max(depth - prev_depth, 0.0)
                    elif length_in is not None and depth_in is None:
                        length = length_in
                        depth = prev_depth + length
                    elif length_in is not None and depth_in is not None:
                        depth = depth_in
                        length = max(depth - prev_depth, 0.0)
                    else:
                        depth = prev_depth
                        length = 0.0

                prev_depth = depth

                if source == "casing":
                    set_table_item(self.table_casing, r, 4, f"{length:.3f}")
                    set_table_item(self.table_casing, r, 5, f"{depth:.3f}")
                else:
                    set_table_item(self.table_openhole, r, 2, f"{length:.3f}")
                    set_table_item(self.table_openhole, r, 3, f"{depth:.3f}")

                if typ == "Casing":
                    known = sum((x is not None and x > 0) for x in (od, id_, wall))
                    if known >= 2:
                        od, id_, wall = compute_casing_params(od, id_, wall)
                    else:
                        od = od or 0.0
                        id_ = id_ or 0.0
                        wall = wall or 0.0
                    self.casings.append(Casing(od, id_, wall, length, name, typ="Casing"))

                elif typ == "Open Hole":
                    eff_diam = id_ if id_ else 0.0
                    self.casings.append(Casing(eff_diam, eff_diam, 0.0, length, name, typ="Open Hole"))

            # --- Суммарная MD конструкции (для модулей 'Равновесие' и 'Отдувка') ---
            total_construction_depth = sum(c.length for c in self.casings)
            logger.debug("Суммарная MD конструкции: %.3f м", total_construction_depth)

            if self.tab_balance is not None:
                self.tab_balance.construction_depth_md = total_construction_depth
            if self.tab_displacement is not None:
                self.tab_displacement.construction_depth_md = total_construction_depth

            # КНБК
            self.bha.clear()
            for r in range(self.table_bha.rowCount()):
                name_raw = self.table_bha.item(r, 0).text() if self.table_bha.item(r, 0) else "BHA"
                name = normalize_bha_name(name_raw)
                length = parse_float_cell(self.table_bha.item(r, 1)) or 0.0
                od = parse_float_cell(self.table_bha.item(r, 2)) or 0.0
                id_val = parse_float_cell(self.table_bha.item(r, 3))
                id_bha = id_val if id_val is not None else 0.0

                if length > 0 and od > 0 and (id_bha >= 0) and (id_bha < od if id_val is not None else True):
                    self.bha.append(BHAElement(name, length, od, id_bha))

            # Корректировка длины верхнего элемента КНБК
            if self.casings and self.bha:
                total_bha_length = sum(b.length for b in self.bha)
                diff = total_construction_depth - total_bha_length
                if abs(diff) > 1e-6:
                    self.bha[0].length += diff
                    set_table_item(self.table_bha, 0, 1, f"{self.bha[0].length:.3f}")
                    logger.debug("Скорректирована длина верхнего элемента КНБК на %.3f м", diff)

            # Жидкости
            self.collect_fluids()

            # Объёмы
            res_lines = calculate_volumes(self.casings, self.bha)
            res_lines.append("")
            res_lines.append(render_fluid_summary(self.fluids))
            self.label_results.setText("\n".join(res_lines))

            # Визуализация
            self.scene.draw_construction(self.casings, self.bha)
            QTimer.singleShot(100, lambda: self.view.fitInView(self.scene.itemsBoundingRect(), Qt.KeepAspectRatio))

            # обновим список OH после пересчёта (если вкладка уже есть)
            try:
                self.tab_indicator_pill.refresh_openhole_list()
            except Exception:
                pass

            logger.debug("Расчёт объёмов и обновление схемы завершены успешно")

        except Exception as e:
            logger.exception("Ошибка в calculate_and_plot")
            QMessageBox.warning(self, "Ошибка расчёта", str(e))

    # ================= Индикаторная пачка: НОВЫЕ callbacks =================

    def get_openhole_intervals(self):
        """
        Возвращает список интервалов Open Hole из table_openhole:
        [(row_index, top_md, bottom_md, nominal_id_mm, current_eff_id_mm)]
        Сейчас nominal_id_mm == eff_id (отдельно номинал не храним).
        """
        res = []
        try:
            if not hasattr(self, "table_openhole"):
                return res

            for r in range(self.table_openhole.rowCount()):
                typ = self.table_openhole.item(r, 0).text() if self.table_openhole.item(r, 0) else ""
                if "Open" not in typ:
                    continue

                eff_id = parse_float_cell(self.table_openhole.item(r, 1))
                length = parse_float_cell(self.table_openhole.item(r, 2))
                depth = parse_float_cell(self.table_openhole.item(r, 3))

                if length is None or depth is None:
                    continue

                bottom_md = float(depth)
                top_md = float(depth - length)
                nominal_id = eff_id  # пока номинал не храним отдельно

                res.append((r, top_md, bottom_md, nominal_id, eff_id))
        except Exception:
            logger.exception("get_openhole_intervals error")

        return res

    def get_indicator_geometry(self):
        """
        Возвращает геометрию для индикаторной пачки:
          casing_profile: список Segment(0..shoe) по ID обсадки
          bha_rows_top_down: [(L, OD, ID)] сверху вниз из текущего self.bha

        Важно: сначала делаем calculate_and_plot(), чтобы:
          - длины/глубины были актуальны
          - верхний элемент КНБК был подогнан под глубину
        """
        from indicator_pill_calc import Segment

        self.calculate_and_plot()

        # casing_profile: только обсадные колонны, подряд сверху вниз
        casing_profile = []
        md = 0.0
        for c in self.casings:
            if getattr(c, "typ", "") != "Casing":
                continue
            L = float(getattr(c, "length", 0.0) or 0.0)
            cid = float(getattr(c, "id", 0.0) or 0.0)
            if L <= 0 or cid <= 0:
                continue
            casing_profile.append(Segment(md, md + L, cid, cid))
            md += L

        # bha_rows_top_down: текущий self.bha уже сверху вниз (как собираем)
        bha_rows = []
        for b in self.bha:
            L = float(getattr(b, "length", 0.0) or 0.0)
            od = float(getattr(b, "od", 0.0) or 0.0)
            idv = float(getattr(b, "id", 0.0) or 0.0)
            if L > 0 and od > 0 and idv >= 0:
                bha_rows.append((L, od, idv))

        return casing_profile, bha_rows

    def apply_openhole_eff_id(self, row_index: int, d_eff_mm: float):
        """
        Записывает Dэфф в выбранную строку Open Hole (колонка 1: 'Эфф. ID').
        """
        if not hasattr(self, "table_openhole"):
            raise ValueError("Не найдена таблица Open Hole.")

        r = int(row_index)
        if r < 0 or r >= self.table_openhole.rowCount():
            raise ValueError("Некорректный индекс строки Open Hole.")

        set_table_item(self.table_openhole, r, 1, f"{float(d_eff_mm):.1f}")

        # пересчитать объёмы/картинку, чтобы обновился Open Hole
        self.calculate_and_plot()

    # =========================== Объёмы: resize ===========================

    def resizeEvent(self, event):
        super().resizeEvent(event)
        try:
            self.view.fitInView(self.scene.itemsBoundingRect(), Qt.KeepAspectRatio)
        except Exception:
            logger.debug("resizeEvent: не удалось fitInView (возможно, сцена ещё пуста)")


if __name__ == "__main__":
    setup_logger()
    logger.info("Запуск WellApp из csg.py")

    app = QApplication(sys.argv)
    window = WellApp()
    window.show()
    sys.exit(app.exec_())
