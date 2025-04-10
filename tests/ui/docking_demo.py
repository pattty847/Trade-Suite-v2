"""
DearPyGui Docking Demo – API ≥ 1.11

Key points
===========
* Uses **configure_app(init_file=…)** (the new way to persist layouts).
* Programmatic docking helpers were removed from DPG – layouts are now created
  interactively and saved to an ini file.
* We still ship a factory layout (`factory_layout.ini`). On first run we load it
  **then** switch persistence to a per‑user file (`user_layout.ini`).
* `tag` replaces the old `id` argument, and tooltips are standalone items.
* Run with `--reset` to delete the user layout and fall back to factory.
"""

from __future__ import annotations

import os
import sys
import dearpygui.dearpygui as dpg

# ---------------------------------------------------------------------------
# Layout files
# ---------------------------------------------------------------------------
DEFAULT_LAYOUT = "factory_layout.ini"   # immutable layout shipped with the app
USER_LAYOUT    = "user_layout.ini"      # mutable per‑user layout (auto‑saved)

# Quick CLI reset -----------------------------------------------------------
if "--reset" in sys.argv and os.path.exists(USER_LAYOUT):
    os.remove(USER_LAYOUT)

# ---------------------------------------------------------------------------
# DearPyGui bootstrap
# ---------------------------------------------------------------------------
dpg.create_context()

# If the user layout does not exist yet, prime the session with the factory
# arrangement so the first launch looks nice.
if not os.path.exists(USER_LAYOUT) and os.path.exists(DEFAULT_LAYOUT):
    dpg.load_init_file(DEFAULT_LAYOUT)

# One call sets docking flags **and** tells DPG where to read/write the ini.
dpg.configure_app(docking=True, docking_space=True, init_file=USER_LAYOUT)

# ---------------------------------------------------------------------------
# Stable window tags (must not change between runs!)
# ---------------------------------------------------------------------------
WINDOW_TAGS: dict[str, int] = {
    name: dpg.generate_uuid() for name in (
        "center", "left", "right", "top", "bottom", "utility"
    )
}

# ---------------------------------------------------------------------------
# UI definition
# ---------------------------------------------------------------------------
with dpg.window(label="Center", tag=WINDOW_TAGS["center"]):
    dpg.add_text(
        "This is the central workspace.\n"
        "Drag‑and‑drop the other windows onto me, onto each other, or anywhere\n"
        "inside the viewport to experiment with docking."
    )

with dpg.window(label="Left", tag=WINDOW_TAGS["left"]):
    dpg.add_text("Left panel content")

with dpg.window(label="Right", tag=WINDOW_TAGS["right"]):
    dpg.add_text("Right panel content")

with dpg.window(label="Top", tag=WINDOW_TAGS["top"]):
    dpg.add_text("Top panel content")

with dpg.window(label="Bottom", tag=WINDOW_TAGS["bottom"]):
    dpg.add_text("Bottom panel content")

with dpg.window(label="Utility", tag=WINDOW_TAGS["utility"], width=260, height=170):
    dpg.add_text("Utility window — dock me anywhere!")
    dpg.add_separator()

    save_factory_btn = dpg.add_button(
        label="Save current layout as FACTORY default",
        callback=lambda: dpg.save_init_file(DEFAULT_LAYOUT),
    )
    with dpg.tooltip(save_factory_btn):
        dpg.add_text("Overwrite factory_layout.ini with the current arrangement")

    save_user_btn = dpg.add_button(
        label="Save current layout as USER layout",
        callback=lambda: dpg.save_init_file(USER_LAYOUT),
    )
    with dpg.tooltip(save_user_btn):
        dpg.add_text("Manual one‑off save if you disable auto‑persistence")

# ---------------------------------------------------------------------------
# Viewport
# ---------------------------------------------------------------------------

dpg.create_viewport(title="DearPyGui Docking Demo", width=1280, height=720)
dpg.setup_dearpygui()
dpg.show_viewport()

dpg.start_dearpygui()
dpg.destroy_context()
