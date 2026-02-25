import sys
import os
import logging

from PyQt5.QtWidgets import QApplication, QWidget, QHBoxLayout, QMessageBox
from PyQt5.QtCore import Qt

# === Инициализация логгера ===
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

try:
    from logger_setup import setup_logger
    logger = setup_logger()
except Exception:
    # fallback, если logger_setup недоступен
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    logger = logging.getLogger("WellApp.main")
    logger.warning("logger_setup недоступен, используется базовая конфигурация logging")

logger.info("Запуск main.py (тест графики)")

# === Импорт графики ===
try:
    from graphics import WellScene, WellView
    logger.debug("Импорт graphics прошёл успешно")
except Exception:
    logger.exception("Ошибка импорта graphics")
    # На этом этапе QApplication ещё нет — ограничимся логом и выходом
    sys.exit(1)


class Dummy:
    """
    Простой класс-заглушка для тестовой отрисовки casings и BHA,
    имитирует объекты с полями length, od, id, typ.
    """
    def __init__(self, length, od=100, id=80, typ="Casing"):
        self.length = length
        self.od = od
        self.id = id
        self.typ = typ

    def __repr__(self):
        return f"Dummy(typ={self.typ!r}, length={self.length}, od={self.od}, id={self.id})"


# === Запуск приложения ===
if __name__ == "__main__":
    logger.info("Запуск GUI-приложения из main.py")

    app = QApplication(sys.argv)
    main = QWidget()
    layout = QHBoxLayout(main)

    # Конструкция скважины
    casings = [
        Dummy(2023, 244.5, 226.7, "Casing"),
        Dummy(153, 230.33, 230.33, "Open Hole"),
        Dummy(1396, 230.33, 230.33, "Open Hole"),
    ]
    logger.debug("Casings: %r", casings)

    # КНБК
    bha = [
        Dummy(0.22, 220.7, 0, "Bit"),
        Dummy(8.60, 178.0, 71.0, "Mud Motor"),
        Dummy(6.00, 178.0, 73.0, "RSS"),  # RSS сейчас не имеет SVG — просто пропустится
        Dummy(18.60, 178.0, 73.0, "MWD"),
    ]
    logger.debug("BHA: %r", bha)

    try:
        scene = WellScene()
        view = WellView(scene, casings, bha)
        layout.addWidget(view)

        main.resize(1200, 800)
        main.setWindowTitle("Well graphics test (main.py)")
        main.show()

        # Первичная отрисовка и подгонка
        scene.draw_construction(casings, bha)
        view.fit_if_possible()

        logger.info("Сцена успешно создана и отрисована")
    except Exception as e:
        logger.exception("Ошибка при создании сцены или отрисовке")
        QMessageBox.critical(main, "Ошибка", f"Ошибка при создании сцены или отрисовке: {e}")

    sys.exit(app.exec_())
