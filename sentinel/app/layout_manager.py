import base64
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PySide6.QtCore import QByteArray, qVersion
from PySide6.QtWidgets import QMainWindow


LOGGER = logging.getLogger(__name__)

LAYOUT_VERSION = 1
CONFIG_DIR = Path("config")
USER_LAYOUT_PATH = CONFIG_DIR / "user_layout_qt.json"
FACTORY_LAYOUT_PATH = CONFIG_DIR / "factory_layout_qt.json"


@dataclass
class LayoutPayload:
    layout_version: int
    qt_version: str
    app_version: str
    state_b64: str
    geometry_b64: str

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "LayoutPayload":
        return cls(
            layout_version=int(value["layout_version"]),
            qt_version=str(value["qt_version"]),
            app_version=str(value["app_version"]),
            state_b64=str(value["state_b64"]),
            geometry_b64=str(value["geometry_b64"]),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "layout_version": self.layout_version,
            "qt_version": self.qt_version,
            "app_version": self.app_version,
            "state_b64": self.state_b64,
            "geometry_b64": self.geometry_b64,
        }


class LayoutManager:
    def __init__(self, app_version: str) -> None:
        self.app_version = app_version
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    def save_layout(self, window: QMainWindow, *, is_default: bool = False) -> Path:
        state = window.saveState()
        geometry = window.saveGeometry()
        payload = LayoutPayload(
            layout_version=LAYOUT_VERSION,
            qt_version=qVersion(),
            app_version=self.app_version,
            state_b64=bytes(state.toBase64()).decode("ascii"),
            geometry_b64=bytes(geometry.toBase64()).decode("ascii"),
        )
        target = FACTORY_LAYOUT_PATH if is_default else USER_LAYOUT_PATH
        target.write_text(json.dumps(payload.to_dict(), indent=2), encoding="utf-8")
        LOGGER.info("Saved Qt layout to %s", target)
        return target

    def restore_layout(self, window: QMainWindow) -> bool:
        for source in (USER_LAYOUT_PATH, FACTORY_LAYOUT_PATH):
            payload = self._load_payload(source)
            if payload is None:
                continue

            ok = window.restoreGeometry(self._decode(payload.geometry_b64))
            ok = bool(window.restoreState(self._decode(payload.state_b64))) and ok
            if ok:
                LOGGER.info("Restored Qt layout from %s", source)
                return True
            LOGGER.warning("Failed to restore layout bytes from %s; trying fallback", source)
        LOGGER.info("No valid persisted Qt layout found; using default arrangement")
        return False

    def reset_user_layout(self) -> None:
        if USER_LAYOUT_PATH.exists():
            USER_LAYOUT_PATH.unlink()
            LOGGER.info("Removed user layout file: %s", USER_LAYOUT_PATH)

    def _load_payload(self, path: Path) -> LayoutPayload | None:
        if not path.exists():
            return None
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            payload = LayoutPayload.from_dict(raw)
        except Exception as exc:
            LOGGER.warning("Failed parsing layout file %s: %s", path, exc)
            return None

        if payload.layout_version != LAYOUT_VERSION:
            LOGGER.warning(
                "Skipping layout %s due to layout_version mismatch (%s != %s)",
                path,
                payload.layout_version,
                LAYOUT_VERSION,
            )
            return None

        if payload.qt_version != qVersion():
            LOGGER.warning(
                "Skipping layout %s due to qt_version mismatch (%s != %s)",
                path,
                payload.qt_version,
                qVersion(),
            )
            return None

        if payload.app_version != self.app_version:
            LOGGER.warning(
                "Skipping layout %s due to app_version mismatch (%s != %s)",
                path,
                payload.app_version,
                self.app_version,
            )
            return None

        return payload

    @staticmethod
    def _decode(value: str) -> QByteArray:
        return QByteArray.fromBase64(value.encode("ascii"))
