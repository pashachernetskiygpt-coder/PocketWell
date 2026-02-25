import math
import logging

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QPushButton, QApplication, QFileDialog, QMessageBox, QStyledItemDelegate,
    QLabel, QLineEdit, QSizePolicy, QHeaderView
)
from PyQt5.QtCore import Qt, QTimer

logger = logging.getLogger("WellApp.trajectory")


class ReadOnlyDelegate(QStyledItemDelegate):
    def createEditor(self, parent, option, index):
        return None


class TrajectoryTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._handling_traj_change = False
        self.balance_tab = None  # будет проставлено снаружи (WellApp)
        logger.debug("Инициализация TrajectoryTab")
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)

        # строка для ввода альтитуды
        altitude_layout = QHBoxLayout()
        altitude_label = QLabel("Альтитуда, м:")
        self.altitude_edit = QLineEdit("0.0")
        altitude_layout.addWidget(altitude_label)
        altitude_layout.addWidget(self.altitude_edit)
        layout.addLayout(altitude_layout)

        # строка для ввода поправки азимута
        azimcorr_layout = QHBoxLayout()
        azimcorr_label = QLabel("Поправка Ази., °:")
        self.azimcorr_edit = QLineEdit("0.0")
        azimcorr_layout.addWidget(azimcorr_label)
        azimcorr_layout.addWidget(self.azimcorr_edit)
        layout.addLayout(azimcorr_layout)

        # таблица
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["MD, м", "Угол, °", "Азимут, °", "TVD, м"])
        self.table.setItemDelegateForColumn(3, ReadOnlyDelegate(self.table))

        # растягивание таблицы по ширине окна
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.horizontalHeader().setStretchLastSection(True)

        # чтобы таблица занимала всё доступное пространство
        self.table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        layout.addWidget(self.table)

        # кнопки
        btns = QHBoxLayout()
        btn_add = QPushButton("Добавить точку")
        btn_add.clicked.connect(self.add_row)

        btn_clear = QPushButton("Очистить")
        btn_clear.clicked.connect(self.clear)

        btn_paste = QPushButton("Вставить из буфера")
        btn_paste.clicked.connect(self.paste)

        btn_load = QPushButton("Загрузить из файла")
        btn_load.clicked.connect(self.load_from_file)

        for btn in (btn_add, btn_clear, btn_paste, btn_load):
            btns.addWidget(btn)
        layout.addLayout(btns)

        self.table.cellChanged.connect(self.on_cell_changed)
        # пересчёт при изменении альтитуды или поправки
        self.altitude_edit.textChanged.connect(
            lambda: QTimer.singleShot(0, self.update_tvd)
        )
        self.azimcorr_edit.textChanged.connect(
            lambda: QTimer.singleShot(0, self.update_tvd)
        )

        self.add_row()

    def add_row(self):
        row = self.table.rowCount()
        self.table.blockSignals(True)
        self.table.insertRow(row)
        self.table.setItem(row, 0, QTableWidgetItem(str(0.0)))
        self.table.setItem(row, 1, QTableWidgetItem(str(0.0)))
        self.table.setItem(row, 2, QTableWidgetItem(str(0.0)))
        self.table.setItem(row, 3, QTableWidgetItem(""))
        self.table.blockSignals(False)
        logger.debug("Добавлена точка траектории, всего строк: %s", self.table.rowCount())
        self.update_tvd()

    def clear(self):
        logger.debug("Очистка таблицы траектории")
        self.table.blockSignals(True)
        self.table.setRowCount(0)
        self.table.blockSignals(False)

    def on_cell_changed(self, row, column):
        if column == 3:
            # столбец TVD — только для вывода
            return
        if self._handling_traj_change:
            return
        self._handling_traj_change = True
        QTimer.singleShot(0, self.update_tvd)
        self._handling_traj_change = False

    def update_tvd(self):
        """
        Простой расчёт TVD по формуле dTVD = dMD * cos(incl).
        Пока без X/Y и минимальной кривизны.
        """
        try:
            # читаем альтитуду
            try:
                altitude = float(self.altitude_edit.text().replace(",", "."))
            except Exception:
                logger.warning("update_tvd: некорректная альтитуда '%s', принята 0.0",
                               self.altitude_edit.text())
                altitude = 0.0

            # читаем поправку азимута
            try:
                azim_corr = float(self.azimcorr_edit.text().replace(",", "."))
            except Exception:
                logger.warning("update_tvd: некорректная поправка азимута '%s', принята 0.0",
                               self.azimcorr_edit.text())
                azim_corr = 0.0

            points = []
            for row in range(self.table.rowCount()):
                try:
                    md_item = self.table.item(row, 0)
                    incl_item = self.table.item(row, 1)
                    azim_item = self.table.item(row, 2)
                    if not md_item or not incl_item or not azim_item:
                        points.append(None)
                        continue

                    md = float(md_item.text().replace(",", "."))
                    incl = float(incl_item.text().replace(",", "."))
                    azim = float(azim_item.text().replace(",", "."))
                    # применяем поправку
                    azim_corrected = azim + azim_corr
                    while azim_corrected >= 360.0:
                        azim_corrected -= 360.0
                    while azim_corrected < 0.0:
                        azim_corrected += 360.0
                    points.append((md, incl, azim_corrected))
                except Exception:
                    points.append(None)

            tvd = altitude   # начинаем с альтитуды
            md_prev = 0.0

            self.table.blockSignals(True)
            for row, p in enumerate(points):
                if p is None:
                    self.table.setItem(row, 3, QTableWidgetItem(""))
                    continue

                md, incl, azim_corr_val = p
                delta_md = md - md_prev
                # прибавляем приращение
                tvd += delta_md * math.cos(math.radians(incl))
                md_prev = md

                tvd_item = QTableWidgetItem(f"{tvd:.2f}")
                tvd_item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                self.table.setItem(row, 3, tvd_item)

                # обновляем ячейку азимута с поправкой
                azim_item = self.table.item(row, 2)
                if azim_item:
                    azim_item.setText(f"{azim_corr_val:.2f}")

            self.table.blockSignals(False)

            # 🔑 Автоматическое обновление во вкладке "Равновесие"
            if getattr(self, "balance_tab", None):
                try:
                    self.balance_tab.update_tvd_display()
                except Exception:
                    logger.exception("update_tvd: ошибка при обновлении BalanceTab")

        except Exception:
            logger.exception("update_tvd: необработанная ошибка")

    def paste(self):
        clipboard = QApplication.clipboard()
        text = clipboard.text()
        logger.debug("paste: вставка траектории из буфера, длина текста=%s", len(text or ""))
        self.load_from_text(text)

    def load_from_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Выберите файл траектории", "", "Text Files (*.txt)"
        )
        if not path:
            return
        try:
            with open(path, encoding="utf-8") as f:
                text = f.read()
            logger.debug("load_from_file: загружено %s символов из %s", len(text), path)
            self.load_from_text(text)
        except Exception as e:
            logger.exception("load_from_file: ошибка загрузки из %s", path)
            QMessageBox.warning(self, "Ошибка загрузки", str(e))

    def load_from_text(self, text: str):
        """
        Загружает траекторию из текста.
        Ожидает формат с тремя колонками: MD, углы, азимут.
        Разделители: пробел, таб или ';'.
        """
        if not text or not text.strip():
            logger.warning("load_from_text: получен пустой текст")
            return

        self.clear()
        lines = text.strip().splitlines()
        logger.debug("load_from_text: обработка %s строк", len(lines))

        self.table.blockSignals(True)
        for line in lines:
            # Удаляем неразрывные пробелы и лишнее
            line = line.replace("\u00A0", " ").strip()
            if not line:
                continue

            # Поддержка форматов: разделитель пробел/таб или ';'
            if ";" in line:
                parts = [p for p in line.split(";") if p.strip()]
            else:
                parts = line.split()

            if len(parts) < 3:
                continue

            try:
                md = float(parts[0].replace(",", "."))
                incl = float(parts[1].replace(",", "."))
                azim = float(parts[2].replace(",", "."))
            except Exception:
                logger.warning("load_from_text: не удалось распарсить строку '%s'", line)
                continue

            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(str(md)))
            self.table.setItem(row, 1, QTableWidgetItem(str(incl)))
            self.table.setItem(row, 2, QTableWidgetItem(str(azim)))
            self.table.setItem(row, 3, QTableWidgetItem(""))

        self.table.blockSignals(False)
        self.update_tvd()
