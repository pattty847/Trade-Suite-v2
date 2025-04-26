# Code Review Findings

## `trade_suite/__main__.py`

**Overall:** Serves correctly as the application entry point (`python -m trade_suite`). Keeps setup logic separate from `__init__.py`, which is good practice.

**Observations & Suggestions:**

1.  **`main()` Function Responsibilities:** The `main` function orchestrates startup but could benefit from further separation of concerns:
    *   **Layout Reset Logic:** The check for `--reset-layout` and subsequent deletion of `user_layout.ini` is UI-specific setup. *Suggestion:* Move this logic closer to the `Viewport` initialization (e.g., inside its `__init__` or a dedicated setup method).
    *   **Exchange Determination Logic:** The logic combining `config.json` settings and command-line arguments to decide `exchanges_to_use` could be extracted into a helper function (e.g., `_determine_exchanges(config, args)`) for clarity.
2.  **Error Handling:** Consider adding `try...except` blocks around critical initializations (like `InfluxDB`, `Data`, `Viewport`) to provide more specific error messages to the user if a component fails to start.
3.  **Platform-Specific Event Loop:** Correctly handles OS differences for `asyncio` event loops. Placement at the top level is appropriate.
4.  **Logging Setup:** `_setup_logging` is well-structured for application runtime logging.

**Future Refactoring Notes:**

*   **Dynamic Exchange Loading:** Investigate loading exchange configurations dynamically. This could involve:
    *   Scanning `.env` for variables matching a pattern (e.g., `EXCHANGE_COINBASE_API_KEY`).
    *   Using these found exchanges to instantiate corresponding `ccxt` exchange objects.
    *   Potentially storing exchange-specific settings (API keys, etc.) securely, perhaps managed via the `ConfigManager` or a dedicated secrets manager.
*   **Configuration Integration:** Ensure the exchange loading mechanism integrates smoothly with `ConfigManager` for retrieving any necessary settings.

---

## `trade_suite/config.py` (`ConfigManager`)

**Overall:** Implements a Singleton pattern to manage UI layout (`.ini`), widget configuration (`.json`), and general application settings (`config.json`). Centralizes configuration access.

**Observations & Suggestions:**

1.  **Singleton Implementation:** Uses `__new__` correctly but mixes instance creation check with initialization logic. Consider using `__init__` with a run-once flag for initialization clarity. Class attributes are used for shared state, which is appropriate for a Singleton.
2.  **Error Handling:** Good use of `try...except` for file I/O and JSON parsing, with reasonable fallbacks (e.g., using default config on load errors).
3.  **Path Management:** Clear methods for retrieving absolute paths. Directory creation is handled proactively.
4.  **Naming Consistency:** Minor inconsistency between "factory" (internal variable) and "default" (method names) for layout/widget files. Suggest standardizing (e.g., use "factory" consistently).
5.  **Dependencies:** Direct import of `dearpygui` couples `ConfigManager` to the UI library. Acceptable for now, but consider isolating DPG calls if `ConfigManager` needs to be used in non-UI contexts.
6.  **Singleton Pattern Considerations:** While convenient, be mindful of global state and testability challenges associated with Singletons. Prefer passing the `ConfigManager` instance via dependency injection where possible (as done with `Viewport`).
