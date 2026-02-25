import logging
import os


def setup_logger(log_file: str = "program_debug.log") -> logging.Logger:
    """
    Настраивает и возвращает корневой логгер приложения "WellApp".

    - Пишет лог в файл и в консоль.
    - Избегает дублирования хендлеров при повторных вызовах.
    """
    log_path = os.path.abspath(log_file)

    logger = logging.getLogger("WellApp")
    logger.setLevel(logging.DEBUG)

    # Если хендлеры уже настроены — ничего не делаем, просто возвращаем логгер
    if logger.handlers:
        return logger

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )

    # Хендлер на файл
    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # Хендлер на консоль
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # Чтобы сообщения не улетали ещё и в root-логгер (и не дублировались)
    logger.propagate = False

    logger.debug(f"Логгер WellApp настроен. Файл лога: {log_path}")
    return logger
