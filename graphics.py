import os
import logging

from PyQt5.QtWidgets import (
    QGraphicsScene,
    QGraphicsView,
    QGraphicsRectItem,
    QGraphicsLineItem,
)
from PyQt5.QtGui import QPainter, QTransform, QColor, QPen
from PyQt5.QtCore import Qt
from PyQt5.QtSvg import QGraphicsSvgItem

logger = logging.getLogger("WellApp.graphics")

# Путь к папке с картинками (относительно проекта)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ASSETS_DIR = os.path.join(BASE_DIR, "img")

SVG_MAP = {
    "Bit": "Bit.svg",
    "Drill Pipe": "Drill Pipe.svg",
    "Heavy Weight": "Heavy Weight.svg",
    "Sub": "Sub.svg",
    "Drill Collar": "Drill Cillar.svg",
    "MWD": "MWD.svg",
    "Jar": "Jar.svg",
    "Stabilizer": "Stabilizer.svg",
    "Mud Motor": "Mud Motor.svg",
    "Casing": "Casing.svg",
    "Open Hole": "Open Hole.svg",
    "Casing Big": "Casing Big.svg",
}

BY_LENGTH_TYPES = {"Drill Pipe", "Heavy Weight", "Casing"}
BY_COUNT_TYPES = {"Bit", "Mud Motor", "Stabilizer", "MWD", "Jar", "Drill Collar", "Sub"}
STRETCH_TYPES = {"Casing Big", "Open Hole"}

EPS = 1e-6


def _get_type(x):
    return (
        getattr(x, "typ", None)
        or getattr(x, "type", None)
        or getattr(x, "name", None)
        or getattr(x, "element_type", None)
        or ""
    )


def _get_od_or_id(x):
    return getattr(x, "od", getattr(x, "id", 0.0)) or 0.0


def _get_length(x):
    return getattr(x, "length", 0.0) or 0.0


def _load_svg_path(typ: str):
    """
    Возвращает путь к SVG-файлу. Если файла нет, возвращает None.
    """
    fname = SVG_MAP.get(typ)
    if not fname:
        return None
    path = os.path.join(ASSETS_DIR, fname)
    if not os.path.exists(path):
        logger.warning("SVG-файл для типа '%s' не найден: %s", typ, path)
        return None
    return path


def add_svg_segmented(
    scene,
    path,
    od,
    length,
    y0,
    z=0,
    direction=1,
    clip_top=None,
    clip_bottom=None,
):
    base_item = QGraphicsSvgItem(path)
    bbox = base_item.boundingRect()
    base_w = bbox.width() or 1.0
    base_h = bbox.height() or 1.0

    scale_x = (od or base_w) / base_w

    def limit(y_start, h):
        if clip_top is None and clip_bottom is None:
            return h
        if direction == 1:
            y_end = y_start + h
            if clip_bottom is not None and y_end > clip_bottom:
                return max(0.0, clip_bottom - y_start)
            return h
        else:
            y_end = y_start - h
            if clip_top is not None and y_end < clip_top:
                return max(0.0, y_start - clip_top)
            return h

    remaining = length
    y_curr = y0

    while remaining >= base_h - EPS:
        vis_h = limit(y_curr, base_h)
        if vis_h <= EPS:
            break
        seg = QGraphicsSvgItem(path)
        tr = QTransform()
        tr.scale(scale_x, vis_h / base_h)
        seg.setTransform(tr)
        pos_y = y_curr if direction == 1 else y_curr - vis_h
        seg.setPos(-od / 2, pos_y)
        seg.setZValue(z)
        scene.addItem(seg)
        y_curr = y_curr + vis_h if direction == 1 else y_curr - vis_h
        remaining -= base_h

    if remaining > EPS:
        vis_h = limit(y_curr, remaining)
        if vis_h > EPS:
            seg = QGraphicsSvgItem(path)
            tr = QTransform()
            tr.scale(scale_x, vis_h / base_h)
            seg.setTransform(tr)
            pos_y = y_curr if direction == 1 else y_curr - vis_h
            seg.setPos(-od / 2, pos_y)
            seg.setZValue(z)
            scene.addItem(seg)
            y_curr = y_curr + vis_h if direction == 1 else y_curr - vis_h

    return y_curr


def add_svg_element(
    scene,
    typ,
    od,
    length,
    y0,
    z=0,
    direction=1,
    clip_top=None,
    clip_bottom=None,
):
    path = _load_svg_path(typ)
    if not path:
        # если картинки нет — ничего не рисуем, просто возвращаем позицию
        return y0

    base_item = QGraphicsSvgItem(path)
    bbox = base_item.boundingRect()
    base_w = bbox.width() or 1.0
    base_h = bbox.height() or 1.0
    scale_x = (od or base_w) / base_w

    if typ in STRETCH_TYPES:
        seg = QGraphicsSvgItem(path)
        tr = QTransform()
        tr.scale(scale_x, (length or base_h) / base_h)
        seg.setTransform(tr)
        pos_y = y0 if direction == 1 else y0 - (length or base_h)
        seg.setPos(-od / 2, pos_y)
        seg.setZValue(z)
        scene.addItem(seg)
        return y0 + (length or base_h) if direction == 1 else y0 - (length or base_h)

    elif typ in BY_LENGTH_TYPES:
        return add_svg_segmented(
            scene, path, od, length, y0, z, direction, clip_top, clip_bottom
        )

    elif typ in BY_COUNT_TYPES:
        item = QGraphicsSvgItem(path)
        tr = QTransform()
        tr.scale(scale_x, 1.0)
        item.setTransform(tr)
        pos_y = y0 if direction == 1 else y0 - base_h
        item.setPos(-od / 2, pos_y)
        item.setZValue(z)
        scene.addItem(item)
        return y0 + base_h if direction == 1 else y0 - base_h

    return y0


class WellScene(QGraphicsScene):
    def __init__(self):
        super().__init__()
        self.pad = 300

        # для последующего рисования жидкостей
        self.total_depth_md = 0.0  # суммарная глубина конструкций (MD) в координатах сцены
        self._fluid_items = []         # прямоугольники жидкостей
        self._fluid_label_items = []   # подписи и выноски для жидкостей

    # --- служебное: очистка жидкостей ---
    def _clear_fluids(self):
        for it in self._fluid_items + self._fluid_label_items:
            try:
                self.removeItem(it)
            except Exception:
                pass
        self._fluid_items = []
        self._fluid_label_items = []


    def draw_construction(self, casings, bha):
        """
        Рисует конструкцию и КНБК. Никаких жидкостей — они добавляются отдельным методом.
        """
        self.clear()
        self._clear_fluids()

        origin_y = 0.0

        # --- Подложка ---
        y_bg = origin_y
        casing_big_depth = 0.0
        open_hole_depth = 0.0

        for c in casings:
            c_type = _get_type(c)
            width = _get_od_or_id(c)
            length = _get_length(c)

            typ_bg = (
                "Open Hole"
                if (c_type or "").strip().lower() == "open hole"
                else "Casing Big"
            )
            y_bg = add_svg_element(self, typ_bg, width, length, y_bg, z=-100, direction=1)

            if typ_bg == "Casing Big":
                casing_big_depth += length
            else:
                open_hole_depth += length

        total_bg_depth = y_bg
        min_depth = 1000.0
        total_bg_depth = max(total_bg_depth, min_depth)

        self.total_depth_md = total_bg_depth  # сохраним для жидкостей

        # --- Фон зонами ---
        view_left = -1000
        view_width = 2000
        view_top = -200
        extra_bottom = 200

        no_pen = QPen()
        no_pen.setStyle(Qt.NoPen)

        # 1. Белый верх
        rect_top = QGraphicsRectItem(view_left, view_top, view_width, origin_y - view_top)
        rect_top.setBrush(QColor(255, 255, 255))
        rect_top.setPen(no_pen)
        rect_top.setZValue(-1000)
        self.addItem(rect_top)

        # 2. Лёгкая порода (Casing Big)
        if casing_big_depth > 0:
            rect_casing = QGraphicsRectItem(
                view_left, origin_y, view_width, casing_big_depth
            )
            rect_casing.setBrush(QColor(185, 162, 135))
            rect_casing.setPen(no_pen)
            rect_casing.setZValue(-1000)
            self.addItem(rect_casing)

        # 3. Open Hole
        if open_hole_depth > 0:
            rect_open = QGraphicsRectItem(
                view_left, origin_y + casing_big_depth, view_width, open_hole_depth
            )
            rect_open.setBrush(QColor(140, 114, 83))
            rect_open.setPen(no_pen)
            rect_open.setZValue(-1000)
            self.addItem(rect_open)

        # 4. Низ
        used_depth = casing_big_depth + open_hole_depth
        rect_bottom = QGraphicsRectItem(
            view_left,
            origin_y + used_depth,
            view_width,
            (total_bg_depth - used_depth) + extra_bottom,
        )
        rect_bottom.setBrush(QColor(111, 91, 66))
        rect_bottom.setPen(no_pen)
        rect_bottom.setZValue(-1000)
        self.addItem(rect_bottom)

        # Ограничиваем сцену
        self.setSceneRect(
            view_left, view_top, view_width, total_bg_depth + extra_bottom + 500
        )

        # --- КНБК ---

        y_bha_up = total_bg_depth
        label_x_offset = 200
        label_y_spacing = 70

        labels = []

        # Обрезаем КНБК выше устья
        max_depth = casing_big_depth + open_hole_depth
        visible_bha = []
        accum_depth = 0.0

        for element in reversed(bha):  # снизу вверх
            if accum_depth + element.length <= max_depth:
                visible_bha.insert(0, element)
                accum_depth += element.length
            else:
                remaining = max_depth - accum_depth
                if remaining > 0:
                    from bha import BHAElement  # локальный импорт, чтобы избежать циклов

                    trimmed = BHAElement(
                        name=element.name + " (обрезано)",
                        length_m=remaining,
                        od_mm=element.od,
                        id_mm=element.id,
                    )
                    visible_bha.insert(0, trimmed)
                break

        logger.debug(
            "BHA элементов (снизу вверх): %s",
            [
                f"{_get_type(b)} L={_get_length(b):.2f}, OD={_get_od_or_id(b):.1f}"
                for b in visible_bha
            ],
        )

        for b in reversed(visible_bha):
            typ = _get_type(b) or "Drill Pipe"
            od = _get_od_or_id(b)
            length = _get_length(b)

            if typ in BY_LENGTH_TYPES:
                y_bha_up = add_svg_element(
                    self,
                    typ,
                    od,
                    length,
                    y_bha_up,
                    z=0,
                    direction=-1,
                    clip_top=origin_y,
                    clip_bottom=total_bg_depth,
                )
            elif typ in BY_COUNT_TYPES:
                y_bha_up = add_svg_element(
                    self, typ, od, None, y_bha_up, z=0, direction=-1
                )
            else:
                y_bha_up = add_svg_element(
                    self, typ, od, length, y_bha_up, z=0, direction=-1
                )

            desired_y = y_bha_up + 5
            labels.append((typ, od, length, desired_y))

        # Подписи
        labels.sort(key=lambda x: x[3])
        last_y = None

        for typ, od, length, desired_y in labels:
            label_y = desired_y
            if last_y is not None and (label_y - last_y) < label_y_spacing:
                label_y = last_y + label_y_spacing

            label = f"{typ} ({od:.1f} мм, {length:.2f} м)"
            text_item = self.addText(label)
            text_item.setDefaultTextColor(Qt.black)
            text_item.setPos(od / 2 + label_x_offset, label_y)
            text_item.setFlag(text_item.ItemIgnoresTransformations, True)

            x1 = float(od) / 2
            y1 = float(desired_y - 5)
            x2 = float(od) / 2 + label_x_offset
            y2 = float(label_y)

            line = QGraphicsLineItem(x1, y1, x2, y2)
            line.setPen(QPen(Qt.black))
            self.addItem(line)

            last_y = label_y

        # финальные границы сцены
        self.setSceneRect(-1000, -self.pad, 2000, total_bg_depth + 2 * self.pad)

    # --- Рисование столбов жидкости + выноски ---
    # --- НОВОЕ: рисование столбов жидкости ---
    def draw_fluids(self, h_t_md, h_a_md, color_t=None, color_a=None):
        """
        Рисует столбы жидкостей в трубах и затрубе + выноски слева.

        h_t_md, h_a_md — высоты столбов в метрах (по MD, но мы принимаем 1:1 с координатами сцены).
        color_t, color_a — QColor или None (если None, используются дефолты).
        """
        # сначала убираем старые столбы/подписи
        self._clear_fluids()

        if self.total_depth_md <= 0:
            logger.debug("draw_fluids: total_depth_md <= 0, ничего не рисуем")
            return

        bottom_y = self.total_depth_md
        center_x = 0

        # условные ширины "затруба" и "труб"
        annulus_width = 140
        tubing_width = 60

        # ограничиваем высоты, чтобы не выходили за низ сцены
        h_t = max(0.0, min(h_t_md, self.total_depth_md))
        h_a = max(0.0, min(h_a_md, self.total_depth_md))

        if h_t <= 0 and h_a <= 0:
            logger.debug("draw_fluids: обе высоты <= 0, ничего не рисуем")
            return

        # Цвета: берём из Fluid.color, если переданы, иначе дефолт
        if color_t is None:
            color_t = QColor(0, 200, 255)
        else:
            color_t = QColor(color_t)
        if color_a is None:
            color_a = QColor(0, 255, 0)
        else:
            color_a = QColor(color_a)

        # делаем жидкости чуть прозрачнее (~20–30% прозрачности)
        for c in (color_t, color_a):
            c.setAlpha(180)

        no_pen = QPen()
        no_pen.setStyle(Qt.NoPen)

        # --- Сначала рисуем затруб ---
        rect_a = None
        if h_a > 0:
            rect_a = QGraphicsRectItem(
                center_x - annulus_width / 2,
                bottom_y - h_a,
                annulus_width,
                h_a,
            )
            rect_a.setBrush(color_a)
            rect_a.setPen(no_pen)
            rect_a.setZValue(5)  # чуть выше КНБК, но просвечивает
            self.addItem(rect_a)
            self._fluid_items.append(rect_a)

        # --- Затем трубы ---
        rect_t = None
        if h_t > 0:
            rect_t = QGraphicsRectItem(
                center_x - tubing_width / 2,
                bottom_y - h_t,
                tubing_width,
                h_t,
            )
            rect_t.setBrush(color_t)
            rect_t.setPen(no_pen)
            rect_t.setZValue(6)
            self.addItem(rect_t)
            self._fluid_items.append(rect_t)

        # --- Выноски слева от колонны ---
        label_x_offset_left = -450  # сдвиг далеко влево, чтобы не лезло на КНБК
        label_y_spacing = 40        # минимальное расстояние между подписями
        labels = []

        # подпись для затруба (если есть)
        if rect_a is not None:
            mid_y_a = rect_a.rect().center().y()
            labels.append(("Затруб", color_a, h_a, mid_y_a))

        # подпись для труб (если есть)
        if rect_t is not None:
            mid_y_t = rect_t.rect().center().y()
            labels.append(("Трубы", color_t, h_t, mid_y_t))

        # сортируем по Y (сверху вниз)
        labels.sort(key=lambda x: x[3])

        last_y = None
        for name, col, height, desired_y in labels:
            label_y = desired_y
            if last_y is not None and (label_y - last_y) < label_y_spacing:
                label_y = last_y + label_y_spacing

            # текст подписи, например: "Раствор 1 (1.20 г/см³)" уже формируется в BalanceTab,
            # но здесь мы ограничимся простым названием + высота
            text = f"{name}: {height:.1f} м"

            text_item = self.addText(text)
            text_item.setDefaultTextColor(Qt.black)
            text_item.setPos(label_x_offset_left, label_y)
            text_item.setFlag(text_item.ItemIgnoresTransformations, True)
            text_item.setZValue(20)
            self._fluid_label_items.append(text_item)

            # линия от полосы жидкости к подписи
            if name == "Затруб" and rect_a is not None:
                x1 = rect_a.rect().left()
                y1 = rect_a.rect().center().y()
            elif name == "Трубы" and rect_t is not None:
                x1 = rect_t.rect().left()
                y1 = rect_t.rect().center().y()
            else:
                x1 = center_x
                y1 = desired_y

            x2 = label_x_offset_left + text_item.boundingRect().width()
            y2 = label_y + text_item.boundingRect().height() / 2

            line = QGraphicsLineItem(x1, y1, x2, y2)
            line.setPen(QPen(Qt.black))
            line.setZValue(19)
            self.addItem(line)
            self._fluid_label_items.append(line)

            last_y = label_y

        logger.debug(
            "draw_fluids: нарисованы столбы h_t=%.2f м, h_a=%.2f м "
            "(bottom_y=%.2f, total_depth_md=%.2f)",
            h_t,
            h_a,
            bottom_y,
            self.total_depth_md,
        )




class WellView(QGraphicsView):
    def __init__(self, scene, casings=None, bha=None):
        super().__init__(scene)
        self.casings = casings or []
        self.bha = bha or []

        self.setRenderHint(QPainter.Antialiasing, True)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorViewCenter)
        self.setDragMode(QGraphicsView.ScrollHandDrag)

        self.min_scale = 0.2
        self.max_scale = 5.0
        self.zoom_factor_per_step = 1.15

        self.scene().draw_construction(self.casings, self.bha)
        self.fit_if_possible()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.fit_if_possible()

    def update_data(self, casings, bha):
        self.casings = casings or []
        self.bha = bha or []
        self.scene().draw_construction(self.casings, self.bha)
        self.fit_if_possible()

    def fit_if_possible(self):
        try:
            br = self.scene().itemsBoundingRect()
            if not br.isNull():
                padded = br.adjusted(-50, -50, 50, 50)
                self.resetTransform()
                self.setSceneRect(padded)
                self.fitInView(padded, Qt.KeepAspectRatio)
        except Exception:
            pass
