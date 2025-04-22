## Feature Implementation Plan: Dynamic Layout Persistence

**Goal:** Implement a system where dynamically added/removed widgets (`DockableWidget` instances) and their Dear PyGui window states (position, size, docking) are saved between application sessions and restored on startup. Leverage `ConfigManager` for persistence and ensure correct loading order within the application lifecycle.

**Core Concepts from Proof-of-Concept (`test_custom_layout.py`):**

1.  **Separation of Concerns:** Widget configuration data (type, instance ID, specific settings) is stored separately (`.json`) from DPG's internal window state (`.ini`).
2.  **Load Order:**
    *   Enable Docking (`dpg.configure_app(docking=True, docking_space=True)`).
    *   Create DPG Viewport (`dpg.create_viewport`).
    *   Setup DPG (`dpg.setup_dearpygui`).
    *   Load widget configuration (`.json`) and recreate `DockableWidget` instances, calling their `create()` methods to generate the DPG windows.
    *   Apply DPG layout (`dpg.configure_app(init_file=...)`) using the `.ini` file.
    *   Show Viewport (`dpg.show_viewport`) and start the render loop.
3.  **Widget Responsibility:** Each widget instance is responsible for creating its own DPG window with a stable, unique tag. The `on_close` callback handles cleanup (like unsubscribing via `TaskManager`) and notifies the manager.
4.  **Manager Responsibility:** A central manager (like `DashboardManager`) tracks active widgets, orchestrates loading/saving, and handles adding/removing widgets based on configuration or user actions.

**Integration Steps into `trade_suite`:**

**Phase 1: Enhance `ConfigManager`**

1.  **Define Paths:** Add configuration settings within `ConfigManager` (or its underlying config source) to specify the file paths for:
    *   DPG Layout File (e.g., `dpg_layout.ini`)
    *   Widget Configuration File (e.g., `widgets.json`)
2.  **DPG Layout Methods:**
    *   `get_dpg_ini_path() -> str`: Returns the absolute path to the `.ini` file.
    *   `save_dpg_layout()`: Calls `dpg.save_init_file(self.get_dpg_ini_path())`. Include logging.
3.  **Widget Configuration Methods:**
    *   `load_widget_config() -> List[Dict[str, Any]]`: Reads the `.json` file. Returns a list of widget definition dictionaries (e.g., `[{"widget_type": "chart", "instance_id": "...", "config": {...}}, ...]`). Handles file-not-found gracefully (return empty list) and JSON parsing errors. Include logging.
    *   `save_widget_config(widget_data: List[Dict[str, Any]])`: Writes the provided list of widget definitions to the `.json` file. Include logging and error handling.

**Phase 2: Enhance `DockableWidget`**

1.  **`get_config() -> Dict[str, Any]` Method:**
    *   Add an *abstract* or *base* method `get_config(self) -> Dict[str, Any]` to `DockableWidget`.
    *   **Subclasses MUST implement this.** It should return a dictionary containing all necessary information to recreate this *specific* widget instance, beyond just `widget_type` and `instance_id`. This includes things like the `title`, any initial parameters passed via `kwargs` in `__init__`, and potentially any runtime-configurable state specific to that widget type.
    *   *Example for a Chart Widget:* `return {"title": self.title, "symbol": self.symbol, "interval": self.interval, ...}`
2.  **Review `__init__`:** Ensure `DockableWidget` and its subclasses store all parameters needed for the `get_config()` method.
3.  **Review `_on_window_close`:** Ensure it reliably informs the `DashboardManager` that the widget is being closed by the user (see Phase 5).

**Phase 3: Modify Application Startup & Layout Loading**

1.  **Refactor Main Application Entry Point (`Viewport` / `Program`):**
    *   Instantiate `ConfigManager`.
    *   Instantiate `TaskManager`, `SignalEmitter`.
    *   Instantiate `DashboardManager`, passing dependencies (`config_manager`, `task_manager`, `emitter`).
    *   `dpg.create_context()`
    *   `dpg.configure_app(docking=True, docking_space=True)` **(Enable Docking)**
    *   `dpg.create_viewport(...)`
    *   `dpg.setup_dearpygui()` **(Setup DPG)**
    *   Call `dashboard_manager.initialize_layout()` (or a renamed equivalent like `load_and_apply_layout`). **(Load Widgets & Layout)**
    *   `dpg.show_viewport()`
    *   `dpg.start_dearpygui()` (or manual render loop)
    *   `dpg.destroy_context()`
2.  **Implement `DashboardManager.initialize_layout()` (or equivalent):**
    *   `logging.info("Loading layout...")`
    *   Get widget data: `widget_definitions = self.config_manager.load_widget_config()`
    *   `logging.info(f"Found {len(widget_definitions)} widget definitions to load.")`
    *   Iterate through `widget_definitions`:
        *   Extract `widget_type`, `instance_id`, `config`.
        *   Call `self.add_widget(widget_type, instance_id, config)` (See Phase 5 for `add_widget` details). This will create the `DockableWidget` instance *and* call its `create()` method, generating the DPG window. Keep track of the successfully created widget tags/instances.
    *   Log state *before* applying INI (optional, but useful for debugging).
    *   Get INI path: `ini_path = self.config_manager.get_dpg_ini_path()`
    *   Check if INI exists: `if os.path.exists(ini_path):`
        *   `logging.info(f"Applying DPG layout from {ini_path}...")`
        *   `dpg.configure_app(init_file=ini_path)` **(Apply INI)**
        *   Handle potential errors during apply.
    *   Else: `logging.info("DPG layout file not found, using default layout.")`
    *   Log state *after* applying INI (optional).
    *   `logging.info("Layout loading complete.")`

**Phase 4: Implement Layout Saving**

1.  **Trigger Mechanism:** Add a "Save Layout" button, menu item, or potentially hook into an application exit event. The callback for this trigger should call a method like `DashboardManager.save_layout()`.
2.  **Implement `DashboardManager.save_layout()`:**
    *   `logging.info("Saving layout...")`
    *   **Save DPG State:** `self.config_manager.save_dpg_layout()`
    *   **Prepare Widget Data:**
        *   `widget_data = []`
        *   Iterate through active widgets tracked by `DashboardManager` (e.g., `self.active_widgets.values()`).
        *   For each `widget`:
            *   `config = widget.get_config()` # Call the new method
            *   `widget_data.append({`
                *   `"widget_type": widget.widget_type,`
                *   `"instance_id": widget.instance_id,`
                *   `"config": config`
            *   `})`
    *   **Save Widget Config:** `self.config_manager.save_widget_config(widget_data)`
    *   `logging.info("Layout saving complete.")`

**Phase 5: Refine Widget Lifecycle Management (`DashboardManager`)**

1.  **Track Active Widgets:** `DashboardManager` needs a dictionary to store active widgets, e.g., `self.active_widgets: Dict[str, DockableWidget] = {}` (mapping `window_tag` to instance might be most direct for removal).
2.  **Implement/Refactor `DashboardManager.add_widget(widget_type, instance_id, config)`:**
    *   Check if widget already exists (based on `instance_id` or generated `window_tag`).
    *   Determine the correct `DockableWidget` subclass based on `widget_type`.
    *   Instantiate the widget: `widget = WidgetClass(emitter=self.emitter, task_manager=self.task_manager, instance_id=instance_id, **config)` (pass necessary dependencies and the loaded config).
    *   Generate `window_tag` (consistency check: should match widget's internal generation).
    *   Call `widget.create()` to build the DPG item. Check return value/handle errors.
    *   If creation is successful, store it: `self.active_widgets[widget.window_tag] = widget`.
3.  **Implement `DashboardManager.handle_widget_closed(window_tag: str)`:**
    *   This method should be called by `DockableWidget._on_window_close`.
    *   `logging.info(f"Handling DPG close event for widget tag: {window_tag}")`
    *   Remove the widget from tracking: `if window_tag in self.active_widgets: del self.active_widgets[window_tag]`
    *   (Note: `DockableWidget._on_window_close` already handles `TaskManager.unsubscribe`).
4.  **Implement/Refactor `DashboardManager.remove_widget(window_tag: str)` (for programmatic removal):**
    *   Find widget: `widget = self.active_widgets.get(window_tag)`
    *   If found:
        *   Call `widget.close()` (this handles unsubscription and `dpg.delete_item`).
        *   Remove from tracking: `del self.active_widgets[window_tag]`.

**Summary & Key Considerations:**

*   This plan centralizes persistence logic in `ConfigManager`.
*   `DashboardManager` orchestrates the lifecycle and application of saved state.
*   `DockableWidget` subclasses are responsible for defining their saveable configuration via `get_config()`.
*   The **load order** defined in Phase 3 is critical for success.
*   Error handling (file I/O, DPG item creation/deletion, subscription) should be robustly implemented.
*   Ensure `window_tag` generation is consistent between `DockableWidget` and how `DashboardManager` might reference it.