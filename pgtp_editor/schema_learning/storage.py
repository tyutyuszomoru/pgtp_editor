from pathlib import Path

from PySide6.QtCore import QStandardPaths

_MODEL_FILENAME = "schema_model.json"
_XSD_FILENAME = "schema.xsd"


def _app_data_dir() -> Path:
    return Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation))


def schema_model_path(base_dir: Path | None = None) -> Path:
    return (base_dir or _app_data_dir()) / _MODEL_FILENAME


def schema_xsd_path(base_dir: Path | None = None) -> Path:
    return (base_dir or _app_data_dir()) / _XSD_FILENAME
