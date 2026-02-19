# Core Services Facade Refactor

**Date:** 2025-06-18

## Summary

The `TaskManager`, `SignalEmitter`, and `DataFacade` have been moved into a new `trade_suite.core` package. A `CoreServicesFacade` was introduced to initialize and wire these pieces together. This facade allows external clients such as the Sentinel alert bot to bootstrap TradeSuite's backend services without the GUI.

## Impact

* The main application and standalone tools now create a `CoreServicesFacade` instead of constructing each service manually.
* Documentation and diagrams updated to reference the `trade_suite.core` modules.
* Future features can import the facade to reuse TradeSuite's data streaming stack with minimal setup.
