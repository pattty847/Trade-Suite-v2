## Feature Implementation Plan: Dynamic Layout Persistence (Refined)

**Goal:** Implement a system where dynamically added/removed widgets (`DockableWidget` instances) and their Dear PyGui window states (position, size, docking) are saved between application sessions and restored on startup. This system will centralize persistence logic within `ConfigManager` and ensure correct loading order within the application lifecycle, mimicking the behavior of `test_custom_layout.py`.

**Core Concepts:**

1.  **Separation of Concerns:**
    *   **`ConfigManager`:** Solely responsible for managing file paths (`.ini`, `.json` for both user and factory defaults) and performing all file I/O operations (reading, writing, deleting).
    *   **`DashboardManager`:** Orchestrates the widget lifecycle (creation, tracking, removal) and the overall saving/loading process by *using* `ConfigManager` for persistence tasks.
    *   **`DockableWidget` Subclasses:** Responsible for providing their specific configuration data needed for recreation via a `get_config()` method.
2.  **Load Order:**
    *   DPG Setup: `create_context`, `configure_app(docking=True)`, `create_viewport`, `setup_dearpygui`.
    *   Call `DashboardManager.initialize_layout()`:
        *   `ConfigManager` loads widget data (`.json`).
        *   `DashboardManager` iterates data, creates `DockableWidget` instances (which create DPG windows).
        *   `ConfigManager` provides user INI path.
        *   `dpg.configure_app(init_file=user_layout.ini, load_init_file=True)` applies the INI layout **after** windows exist.
    *   Conditional Default Widgets: If `initialize_layout` indicates no widgets were loaded from config, `Viewport` calls `DashboardProgram.initialize()` to create defaults.
    *   Show Viewport & Start Loop: `dpg.show_viewport()`, `dpg.start_dearpygui()`.
3.  **Widget Responsibility:** Each widget instance is responsible for:
    *   Creating its own DPG window with a stable, unique tag derived from its `widget_type` and `instance_id`.
    *   Implementing `get_config()` to return the necessary constructor arguments for its recreation.
    *   Handling its `_on_window_close` callback for cleanup (e.g., `TaskManager.unsubscribe`).
4.  **Manager Responsibility:**
    *   `ConfigManager`: Manages paths and file I/O.
    *   `DashboardManager`: Tracks active widgets (`self.widgets`), orchestrates loading/saving by calling `ConfigManager` and `widget.get_config()`, handles adding/removing widgets.

**Integration Steps into `trade_suite`:**

**Phase 1: Enhance `ConfigManager` (`trade_suite/config.py`) [x]**

1.  [x] **Define Path Methods:** Implement methods to return absolute paths:
    *   [x] `get_user_layout_ini_path() -> str`
    *   [x] `get_factory_layout_ini_path() -> str`
    *   [x] `get_user_widgets_json_path() -> str`
    *   [x] `get_default_widgets_json_path() -> str` (e.g., derive from factory INI path)
2.  [x] **Implement File I/O Methods:**
    *   [x] `save_dpg_layout(is_default: bool = False)`: Calls `dpg.save_init_file()` using the appropriate path (user or factory). Include logging.
    *   [x] `load_widget_config() -> List[Dict[str, Any]]`: Reads the *user* `.json` file. Returns a list of widget definition dictionaries. Handles file-not-found (return empty list) and JSON parsing errors gracefully. Include logging.
    *   [x] `save_widget_config(widget_data: List[Dict[str, Any]], is_default: bool = False)`: Writes the provided list of widget definitions to the appropriate `.json` file (user or default). Include logging and error handling (`json.dump`, file I/O).
    *   [x] `delete_user_layout()`: Safely deletes the user `.ini` file using `os.remove`. Include logging.
    *   [x] `delete_user_widget_config()`: Safely deletes the user `.json` file using `os.remove`. Include logging.
    *   [x] *(Optional)* `ensure_config_directories()`: Method to create `config/` directory if missing.

**Phase 2: Enhance `DockableWidget` and Subclasses [x]**

1.  [x] **Add Abstract `get_config()` (`trade_suite/gui/widgets/base_widget.py`):**
    *   [x] Add `@abstractmethod def get_config(self) -> Dict[str, Any]: raise NotImplementedError(...)` to `DockableWidget`.
2.  [x] **Implement `get_config()` in Subclasses:**
    *   [x] **`ChartWidget`**: `return {"exchange": self.exchange, "symbol": self.symbol, "timeframe": self.timeframe}`
    *   [x] **`OrderbookWidget`**: `return {"exchange": self.exchange, "symbol": self.symbol}`
    *   [x] **`PriceLevelWidget`**: `return {"exchange": self.exchange, "symbol": self.symbol, "max_depth": self.max_depth, "tick_size": self.tick_size}`
    *   [x] **`TradingWidget`**: `return {"exchange": self.exchange, "symbol": self.symbol}`
    *   [x] **`SECFilingViewer`**: `return {"ticker": self._last_requested_ticker}`
3.  [x] **Review `__init__` Methods:** Ensure widget subclass constructors accept the exact keys returned by their respective `get_config` implementations. (Verified during investigation).

**Phase 3: Refactor `DashboardManager` (`trade_suite/gui/widgets/dashboard_manager.py`)**

1.  **Update `__init__`:**
    *   Remove `default_layout_file`, `user_layout_file`, `user_widgets_file` parameters.
    *   Accept `config_manager: ConfigManager` as a dependency. Store it as `self.config_manager`.
    *   Remove `self.default_layout`, `self.user_layout`, `self.user_widgets` attributes.
    *   Remove call to `_ensure_layout_directories` (should be handled by `ConfigManager` or main app setup).
2.  **Refactor `initialize_layout()`:**
    *   Change signature to `initialize_layout(self, reset: bool = False) -> bool:`.
    *   **Reset Logic:** If `reset` is `True`, call `self.config_manager.delete_user_layout()` and `self.config_manager.delete_user_widget_config()`.
    *   **Load Widgets:**
        *   Call `widget_definitions = self.config_manager.load_widget_config()`.
        *   Iterate `widget_definitions`, extract `instance_id`, `widget_type`, `config`.
        *   Use `self.widget_classes` mapping to get `WidgetClass`.
        *   Instantiate widget: `widget_instance = WidgetClass(emitter=self.emitter, task_manager=self.task_manager, instance_id=instance_id, **common_args, **config)`. Pass required dependencies (`sec_fetcher` if needed).
        *   Call `self.add_widget(instance_id, widget_instance, _loading_layout=True)`.
        *   Keep track if any widgets were successfully recreated (`widgets_recreated = True`).
    *   **Apply DPG Layout:**
        *   Get INI path: `ini_path = self.config_manager.get_user_layout_ini_path()`.
        *   Get INI save target: `ini_save_target = self.config_manager.get_user_layout_ini_path()`.
        *   Determine if INI should be loaded: `should_load_ini = os.path.exists(ini_path)`.
        *   Call `dpg.configure_app(docking=True, docking_space=True, init_file=ini_save_target, load_init_file=should_load_ini)`. Handle potential errors.
    *   **Return Status:** `return widgets_recreated`.
3.  **Refactor `save_layout()`:**
    *   **Save DPG State:** `self.config_manager.save_dpg_layout(is_default=False)`
    *   **Prepare Widget Data:**
        *   `widget_data = []`
        *   Iterate `self.widgets.items()`:
            *   Call `config = widget.get_config()` (ensure robust error handling per widget).
            *   Append `{"instance_id": instance_id, "widget_type": widget.widget_type, "config": config}` to `widget_data`.
    *   **Save Widget Config:** `self.config_manager.save_widget_config(widget_data, is_default=False)`
4.  **Refactor `reset_to_default()`:**
    *   Clear current widgets via `self.remove_widget()`.
    *   Call `self.config_manager.delete_user_layout()`.
    *   Call `self.config_manager.delete_user_widget_config()`.
    *   Call `self.initialize_layout()` again.
5.  **Refactor `save_as_default()`:**
    *   Call `self.config_manager.save_dpg_layout(is_default=True)`.
    *   Prepare widget data list (as in `save_layout`).
    *   Call `self.config_manager.save_widget_config(widget_data, is_default=True)`.
6.  **Remove Helpers:** Delete `_load_widget_config` and `_prepare_widget_config_data` methods.

### Phase 3 Notes and Reasoning: 

**Application Startup & Layout Initialization Flow:**

1.  **Viewport Entry (`Viewport.__enter__`)**: This is the high-level context manager for the GUI. It loads the CCXT exchanges, sets up DPG context, loads font and theme, then calls `DashboardManager.initialize_layout()`.
2.  **`DashboardManager.initialize_layout(reset=False)` Called**: This is the first attempt to restore the user's previous session state. Let's dive deep into this function:

    *   **Purpose**: To recreate the widgets and their DPG window layout based on previously saved configuration files managed by `ConfigManager`. It aims to restore the user's workspace exactly as they left it.
    *   **`reset` Parameter**: If `True`, the function first tells `ConfigManager` to delete the user's saved layout (`.ini`) and widget configuration (`.json`). This is used by the "Reset to Default" action. For normal startup, it's `False`.
    *   **Load Widget Definitions**:
        *   It calls `widget_definitions = self.config_manager.load_widget_config()`.
        *   `ConfigManager` handles finding the correct file (user's `widgets.json` first, potentially falling back to a default/factory `widgets.json` if the user's doesn't exist or is invalid, though the primary goal is loading the *user's* config).
        *   This loads a list of dictionaries, where each dictionary represents a widget instance and contains:
            *   `instance_id`: The unique ID given to that specific widget (e.g., "binance_chart_1").
            *   `widget_type`: A string identifying the class of the widget (e.g., "chart", "orderbook").
            *   `config`: A dictionary containing the specific state saved by that widget's `get_config()` method (e.g., `{"exchange": "binance", "symbol": "BTC/USDT", "timeframe": "1h"}` for a chart).
    *   **Widget Recreation Loop**:
        *   It iterates through the `widget_definitions` list.
        *   For each `definition`:
            *   It extracts `instance_id`, `widget_type`, and the specific `config` dictionary.
            *   It looks up the actual widget class (e.g., `ChartWidget`, `OrderbookWidget`) using the `widget_type` string as a key in the `self.widget_classes` dictionary. This allows dynamic instantiation based on the saved type.
            *   It prepares `common_args`: a dictionary containing dependencies needed by *most* widgets (`emitter`, `task_manager`, the specific `instance_id`).
            *   It checks if the `WidgetClass` requires specific dependencies (like `SECFilingViewer` needing `sec_fetcher`) and adds them to `common_args`.
            *   **Crucially, it instantiates the widget**: `widget_instance = WidgetClass(**common_args, **config)`. The `**config` unpacks the saved state (like symbol, timeframe) and passes it to the widget's `__init__`, allowing it to initialize itself with its previous settings.
            *   It calls `self.add_widget(instance_id, widget_instance, _loading_layout=True)`:
                *   `add_widget` stores the `widget_instance` in the `self.widgets` registry.
                *   `add_widget` calls `widget_instance.create()`, which is responsible for building the DPG window and its internal elements for that specific widget. Crucial for a working dynamic persistent widget system where widgets added during runtime reappear if the layout is saved.
                *   `_loading_layout=True` prevents `add_widget` from immediately setting `self.layout_modified = True`. We only consider the layout modified by user actions *after* initialization.
            *   If `add_widget` is successful (returns a window tag), it sets `widgets_recreated = True`. This flag tracks whether we actually loaded *any* widgets from the config.
            *   Error handling logs issues if definitions are invalid, instantiation fails, or widget types are unknown.
    *   **Apply DPG Layout (Window Positions/Docking)**:
        *   Gets the user's layout INI file path from `ConfigManager`: `ini_save_path = self.config_manager.get_user_layout_ini_path()`.
        *   Checks if this file exists: `should_load_ini = os.path.exists(ini_save_path)`.
        *   Calls `dpg.configure_app()`:
            *   `docking=True`, `docking_space=True`: Enables DPG's docking system.
            *   `init_file=ini_save_path`: **This tells DPG where to SAVE the layout INI file when the app closes normally.** It defines the *output* path for the layout state.
            *   `load_init_file=should_load_ini`: **This tells DPG whether to LOAD window states (position, size, docking nodes) from the `init_file` path *right now*.** If `should_load_ini` is `True`, DPG reads the specified `.ini` file and attempts to apply the saved positions and docking structure to the DPG windows that were just created in the widget recreation loop (matching them by their labels/tags). If `False` (the `.ini` file didn't exist), DPG uses its default window placement logic.
    *   **Finalization**:
        *   Sets `self.layout_modified = False`. The layout is now considered "saved" or "initial", even if it was just loaded.
        *   Returns `widgets_recreated` (Boolean).

3.  **`DashboardProgram.initialize()`**: This method is called after `DashboardManager.initialize_layout()`.
    *   It likely checks the return value of `initialize_layout`.
    *   **Scenario A: `initialize_layout()` returned `True`**: This means the user's widgets and layout were successfully loaded from their saved configuration. `DashboardProgram.initialize` might skip creating default widgets, as the user's desired state has been restored.
    *   **Scenario B: `initialize_layout()` returned `False`**: This means no user widget configuration was found or loaded (e.g., first run, or user deleted config). In this case, `DashboardProgram.initialize` proceeds to call `_create_widgets_for_exchange()` for each configured exchange.
4.  **`DashboardProgram._create_widgets_for_exchange()`**:
    *   This function is called *only* if `initialize_layout` indicated that no prior widget state was loaded.
    *   It programmatically creates a default set of widgets (Chart, Orderbook, Trading, etc.) for a given exchange.
    *   For each widget it creates, it calls `self.dashboard_manager.add_widget(instance_id, widget_instance)`. Note that `_loading_layout` is likely `False` here (or omitted, defaulting to `False`), meaning adding these default widgets *will* mark the layout as modified (`self.layout_modified = True`), prompting a save on exit.

**Saving the Layout:**

1.  **User Interaction**: The user moves windows, docks them, changes settings within widgets (e.g., symbol, timeframe). Changing widget settings (like symbol) might trigger `widget.get_config()` internally if the widget needs to persist that state immediately, but importantly, moving/docking windows implicitly changes the DPG state managed by `dpg.save_init_file`. Adding/removing widgets explicitly calls methods that set `self.layout_modified = True`.
2.  **`DashboardManager.save_layout()`**: Called manually (e.g., via a "Save Layout" button) or automatically on application exit.
    *   Calls `self.config_manager.save_dpg_layout(is_default=False)`:
        *   `ConfigManager` gets the user INI path.
        *   `ConfigManager` likely calls `dpg.save_init_file(user_ini_path)`. This tells DPG to write the current window positions, sizes, and docking state to the user's `.ini` file.
    *   Builds `widget_data`: Iterates through `self.widgets.values()`, calling `widget.get_config()` on each to get its current state dictionary.
    *   Calls `self.config_manager.save_widget_config(widget_data, is_default=False)`:
        *   `ConfigManager` gets the user JSON path.
        *   `ConfigManager` saves the collected `widget_data` list as JSON to the user's `widgets.json` file.
    *   Resets `self.layout_modified = False`.

**Summary Cycle:**

*   **Start**: `initialize_layout` attempts to load user config (JSON for widget state, INI via DPG for layout).
*   **First Run/Reset**: If load fails, `DashboardProgram` creates default widgets.
*   **Runtime**: User interacts, potentially modifying layout (`layout_modified = True`) and widget state (captured by `get_config`).
*   **Save/Exit**: `save_layout` persists widget state (via `get_config` -> JSON) and DPG layout (via `dpg.save_init_file` -> INI).
*   **Next Start**: `initialize_layout` loads the saved JSON and tells DPG to load the saved INI, restoring the state.

This detailed flow should help pinpoint where things might go wrong during loading, saving, or widget recreation.


**Phase 4: Modify Application Startup (`Viewport`, `__main__`)**

1.  **Instantiate `ConfigManager`:** Ensure `ConfigManager()` is instantiated early in the application setup (e.g., in `__main__.py` or `Viewport.__init__`).
2.  **Inject `ConfigManager`:** Pass the `ConfigManager` instance to the `DashboardManager` constructor in `Viewport`.
3.  **Conditional Default Widgets (`Viewport.start_program` or similar):**
    *   `widgets_loaded = self.dashboard_manager.initialize_layout()`
    *   `if not widgets_loaded:`
        *   `logging.info("No saved widgets loaded, initializing default program layout.")`
        *   `self.dashboard_program.initialize()`
    *   `else:`
        *   `logging.info(f"Loaded {len(self.dashboard_manager.widgets)} widgets from configuration.")`

**Summary & Key Considerations:**

*   This refined plan centralizes all persistence I/O and path logic in `ConfigManager`.
*   `DashboardManager` orchestrates the lifecycle and delegates persistence tasks.
*   `DockableWidget` subclasses define their state via `get_config()`.
*   The **load order** and **conditional default widget loading** defined in Phase 4 are critical.
*   Robust error handling (file I/O, JSON parsing, DPG calls, `get_config` calls) is essential throughout.