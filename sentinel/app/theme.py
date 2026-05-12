"""Centralized design tokens and stylesheet loader for the Sentinel UI.

Sentinel uses a single dark palette across both QSS rules and the inline
`setStyleSheet(...)` calls scattered in widgets / pyqtgraph plots. Keeping
every hex value in one place prevents drift and makes it easy to retune the
look without hunting through individual files.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QColor


# ── Palette ────────────────────────────────────────────────────────────
# Names describe role, not literal hue. Use these constants rather than
# inlining hex strings.

class Colors:
    # Backgrounds (darkest → most elevated)
    BG_CANVAS   = "#060a11"   # plot / drawing surface
    BG_APP      = "#0b0f14"   # main window
    BG_PANEL    = "#0d131b"   # toolbars, status bar, dock title
    BG_PANEL_2  = "#0f1620"   # menus, dropdown list
    BG_ELEV     = "#111924"   # inputs, buttons (default)
    BG_HOVER    = "#172131"   # control hover
    BG_PRESSED  = "#0c1520"   # control pressed
    BG_ACTIVE   = "#152338"   # checked / active control
    BG_SELECT   = "#1a2638"   # list / menu selection

    # Borders (subtle → strong)
    BORDER_GRID    = "#131d2c"  # table gridlines
    BORDER_FAINT   = "#162231"  # internal separators
    BORDER_SUB     = "#1a2535"  # default separators
    BORDER_STRIP   = "#192536"  # toolbar bottom strip
    BORDER         = "#253446"  # control border
    BORDER_HOVER   = "#3a5878"  # control hover border
    BORDER_FOCUS   = "#3d6090"  # focused control border
    BORDER_PLOT    = "#1e2d3f"  # pyqtgraph axis pen

    # Text
    TEXT_PRIMARY   = "#d4dae3"
    TEXT_SECONDARY = "#b8c8d8"
    TEXT_MUTED     = "#8fa4c2"
    TEXT_DIM       = "#7a99be"
    TEXT_FAINT     = "#6a85a8"
    TEXT_GHOST     = "#3f5a76"

    # Accent (cool steel-blue brand)
    ACCENT         = "#8fb3ff"
    ACCENT_DIM     = "#6a85a8"
    ACCENT_DEEP    = "#1a3d6a"
    ACCENT_LINE    = "#2d6aaa"

    # Semantic
    UP             = "#26a69a"
    DOWN           = "#ef5350"
    WARN           = "#ffba00"
    INFO           = "#2196f3"

    # Compound (used by inline pyqtgraph styling)
    AXIS_PEN       = BORDER_PLOT
    TICK_PEN       = "#546d8a"
    LABEL_DIM      = TEXT_GHOST
    GRID_ALPHA     = 0.15


# ── Spacing ───────────────────────────────────────────────────────────

class Spacing:
    XS = 2
    S  = 4
    M  = 6
    L  = 8
    XL = 12


# ── Helpers ────────────────────────────────────────────────────────────

def qcolor(hex_str: str, alpha: int | None = None) -> QColor:
    c = QColor(hex_str)
    if alpha is not None:
        c.setAlpha(alpha)
    return c


def pg_label_css() -> dict[str, str]:
    """Inline CSS dict used by pyqtgraph `setLabel(... **css)` calls."""
    return {"color": Colors.LABEL_DIM, "font-size": "10pt"}


def load_qss() -> str:
    """Load the Sentinel stylesheet, substituting palette tokens.

    `theme.qss` uses ``@TOKEN@`` placeholders (e.g. ``@BG_APP@``) which are
    replaced by the matching :class:`Colors` attribute. Using ``@…@`` instead
    of ``{…}`` keeps QSS selector braces intact.
    """
    qss_path = Path(__file__).parent / "theme.qss"
    raw = qss_path.read_text(encoding="utf-8")
    for name in dir(Colors):
        if not name.isupper():
            continue
        value = getattr(Colors, name)
        if not isinstance(value, str):
            continue
        raw = raw.replace(f"@{name}@", value)
    return raw
