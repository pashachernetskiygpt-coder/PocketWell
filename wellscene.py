import sys
import logging

from PyQt5.QtWidgets import QApplication, QWidget, QHBoxLayout
from PyQt5.QtCore import Qt

from graphics import WellScene, WellView

# Пытаемся использовать общий логгер приложения, если он есть
try:
    from logger_setup import setup_logger
    setup_logger()
except Exception:
    # Если logger_setup недоступен (например, при отдельном запуске этого файла),
    # просто включаем базовую конфигурацию, чтобы хоть что-то видеть в консоли.
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

logger = logging.getLogger("WellApp.wellscene")


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


if __name__ == "__main__":
    logger.info("Запуск тестовой сцены WellScene/WellView (wellscene.py)")

    app = QApplication(sys.argv)
    main = QWidget()
    layout = QHBoxLayout(main)

    # тестовые данные конструкции
    casings = [
        Dummy(2023, 244.5, 226.7, "Casing"),
        Dummy(153, 230.33, 230.33, "Open Hole"),
        Dummy(1396, 230.33, 230.33, "Open Hole"),
    ]

    # тестовые данные КНБК
    bha = [
        Dummy(0.22, 220.7, 0, "Bit"),
        Dummy(8.60, 178.0, 71.0, "Mud Motor"),
        Dummy(6.00, 178.0, 73.0, "RSS"),         # для RSS сейчас нет SVG — просто пропустится
        Dummy(18.60, 178.0, 73.0, "MWD"),
        Dummy(55.86, 127.0, 76.0, "Heavy Weight"),
        Dummy(84.12, 127.0, 76.0, "Heavy Weight"),
        Dummy(6.79, 170.0, 70.0, "Jar"),
        Dummy(208.69, 127.0, 108.62, "Drill Pipe"),
        Dummy(3160.42, 127.0, 108.62, "Drill Pipe"),
    ]

    logger.debug("Test casings: %r", casings)
    logger.debug("Test BHA: %r", bha)

    # создаём сцену и вид
    scene = WellScene()
    view = WellView(scene, casings, bha)

    layout.addWidget(view)
    main.resize(1200, 800)
    main.setWindowTitle("WellScene test")
    main.show()

    # Дополнительно подгоним вид (на случай изменений в WellView)
    scene.draw_construction(casings, bha)
    view.fitInView(scene.itemsBoundingRect(), Qt.KeepAspectRatio)

    sys.exit(app.exec_())
