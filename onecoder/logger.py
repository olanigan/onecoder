import logging
from pathlib import Path
from logging.handlers import RotatingFileHandler


def configure_logging(verbose: bool = False):
    """Configures logging for the OneCoder CLI."""

    # define logs directory
    log_dir = Path.home() / ".onecoder" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "onecoder.log"

    # Set base level
    level = logging.DEBUG if verbose else logging.INFO

    # Create root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Clear existing handlers
    if root_logger.handlers:
        root_logger.handlers.clear()

    # File Handler (Always logs DEBUG)
    file_handler = RotatingFileHandler(
        log_file, maxBytes=10 * 1024 * 1024, backupCount=5
    )
    file_handler.setLevel(logging.DEBUG)
    file_formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    file_handler.setFormatter(file_formatter)
    root_logger.addHandler(file_handler)

    # Console Handler (Logs INFO by default, DEBUG if verbose)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_formatter = logging.Formatter("%(message)s")  # Simple format for console
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)

    logging.debug(f"Logging initialized. Verbose: {verbose}")
    return log_file
