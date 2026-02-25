# project_manager_dialog.py
import logging
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTreeWidget, QTreeWidgetItem,
    QPushButton, QInputDialog, QMessageBox
)
from PyQt5.QtCore import Qt

from models_cases import ProjectStore, ProjectNode, FieldNode, WellNode, CaseData

logger = logging.getLogger("WellApp.projects")


class ProjectManagerDialog(QDialog):
    """
    Простое окно с иерархией Проект → Месторождение → Скважина → Кейс.
    Умеет:
      - отображать ProjectStore в QTreeWidget,
      - добавлять/удалять узлы,
      - выбирать кейс.
    Сохранение/загрузка данных кейса в UI мы будем делать в WellApp.
    """

    def __init__(self, store: ProjectStore, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Управление проектами / кейсами")
        self.resize(500, 600)

        self.store = store
        self.selected_case_path = None  # (p_idx, f_idx, w_idx, c_idx)

        layout = QVBoxLayout(self)

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        layout.addWidget(self.tree)

        btns_top = QHBoxLayout()
        self.btn_add_proj = QPushButton("Проект")
        self.btn_add_field = QPushButton("Месторождение")
        self.btn_add_well = QPushButton("Скважина")
        self.btn_add_case = QPushButton("Кейс")
        self.btn_delete = QPushButton("Удалить")

        for b in (self.btn_add_proj, self.btn_add_field,
                  self.btn_add_well, self.btn_add_case, self.btn_delete):
            btns_top.addWidget(b)
        layout.addLayout(btns_top)

        btns_bottom = QHBoxLayout()
        self.btn_use_case = QPushButton("Загрузить кейс в программу")
        self.btn_close = QPushButton("Закрыть")
        btns_bottom.addWidget(self.btn_use_case)
        btns_bottom.addStretch()
        btns_bottom.addWidget(self.btn_close)
        layout.addLayout(btns_bottom)

        # сигналы
        self.btn_add_proj.clicked.connect(self.on_add_project)
        self.btn_add_field.clicked.connect(self.on_add_field)
        self.btn_add_well.clicked.connect(self.on_add_well)
        self.btn_add_case.clicked.connect(self.on_add_case)
        self.btn_delete.clicked.connect(self.on_delete)
        self.btn_use_case.clicked.connect(self.on_use_case)
        self.btn_close.clicked.connect(self.accept)

        self.tree.itemSelectionChanged.connect(self.on_selection_changed)

        self.populate_tree()

    # --- вспомогательное: заполнение дерева ---

    def populate_tree(self):
        self.tree.clear()
        for p_idx, proj in enumerate(self.store.projects):
            p_item = QTreeWidgetItem([proj.name])
            p_item.setData(0, Qt.UserRole, ("project", p_idx))
            self.tree.addTopLevelItem(p_item)

            for f_idx, fld in enumerate(proj.fields):
                f_item = QTreeWidgetItem([fld.name])
                f_item.setData(0, Qt.UserRole, ("field", p_idx, f_idx))
                p_item.addChild(f_item)

                for w_idx, well in enumerate(fld.wells):
                    w_item = QTreeWidgetItem([well.name])
                    w_item.setData(0, Qt.UserRole, ("well", p_idx, f_idx, w_idx))
                    f_item.addChild(w_item)

                    for c_idx, case in enumerate(well.cases):
                        c_item = QTreeWidgetItem([case.name])
                        c_item.setData(0, Qt.UserRole, ("case", p_idx, f_idx, w_idx, c_idx))
                        w_item.addChild(c_item)

        self.tree.expandAll()

    # --- выбор ---

    def on_selection_changed(self):
        item = self.tree.currentItem()
        if not item:
            self.selected_case_path = None
            return
        data = item.data(0, Qt.UserRole)
        if not data:
            self.selected_case_path = None
            return
        kind = data[0]
        if kind == "case":
            _, p, f, w, c = data
            self.selected_case_path = (p, f, w, c)
        else:
            self.selected_case_path = None

    # --- добавление узлов ---

    def _ask_name(self, title, text):
        name, ok = QInputDialog.getText(self, title, text)
        return (name.strip(), ok) if ok and name.strip() else (None, False)

    def on_add_project(self):
        name, ok = self._ask_name("Новый проект", "Название проекта:")
        if not ok:
            return
        self.store.projects.append(ProjectNode(name=name))
        self.populate_tree()

    def on_add_field(self):
        item = self.tree.currentItem()
        if not item:
            QMessageBox.warning(self, "Месторождение", "Сначала выберите проект.")
            return
        data = item.data(0, Qt.UserRole)
        if not data:
            return
        kind = data[0]
        if kind == "project":
            p_idx = data[1]
        elif kind == "field":
            p_idx = data[1]
        else:
            QMessageBox.warning(self, "Месторождение", "Выберите проект или месторождение.")
            return
        name, ok = self._ask_name("Новое месторождение", "Название месторождения:")
        if not ok:
            return
        self.store.projects[p_idx].fields.append(FieldNode(name=name))
        self.populate_tree()

    def on_add_well(self):
        item = self.tree.currentItem()
        if not item:
            QMessageBox.warning(self, "Скважина", "Сначала выберите месторождение.")
            return
        data = item.data(0, Qt.UserRole)
        if not data:
            return
        kind = data[0]
        if kind == "field":
            _, p_idx, f_idx = data
        elif kind == "well":
            _, p_idx, f_idx, _ = data
        else:
            QMessageBox.warning(self, "Скважина", "Выберите месторождение или скважину.")
            return
        name, ok = self._ask_name("Новая скважина", "Название скважины:")
        if not ok:
            return
        self.store.projects[p_idx].fields[f_idx].wells.append(WellNode(name=name))
        self.populate_tree()

    def on_add_case(self):
        item = self.tree.currentItem()
        if not item:
            QMessageBox.warning(self, "Кейс", "Сначала выберите скважину.")
            return
        data = item.data(0, Qt.UserRole)
        if not data:
            return
        kind = data[0]
        if kind == "well":
            _, p_idx, f_idx, w_idx = data
        elif kind == "case":
            _, p_idx, f_idx, w_idx, _ = data
        else:
            QMessageBox.warning(self, "Кейс", "Выберите скважину или существующий кейс.")
            return

        name, ok = self._ask_name("Новый кейс", "Название кейса:")
        if not ok:
            return
        self.store.projects[p_idx].fields[f_idx].wells[w_idx].cases.append(
            CaseData(name=name)
        )
        self.populate_tree()

    def on_delete(self):
        # простая версия: удаляем выбранный узел и всё, что ниже
        item = self.tree.currentItem()
        if not item:
            return
        data = item.data(0, Qt.UserRole)
        if not data:
            return
        kind = data[0]
        if kind == "project":
            _, p = data
            del self.store.projects[p]
        elif kind == "field":
            _, p, f = data
            del self.store.projects[p].fields[f]
        elif kind == "well":
            _, p, f, w = data
            del self.store.projects[p].fields[f].wells[w]
        elif kind == "case":
            _, p, f, w, c = data
            del self.store.projects[p].fields[f].wells[w].cases[c]
        self.populate_tree()

    def on_use_case(self):
        if not self.selected_case_path:
            QMessageBox.warning(self, "Кейс", "Выберите кейс в дереве.")
            return
        self.accept()  # диалог закроется, WellApp прочитает selected_case_path
