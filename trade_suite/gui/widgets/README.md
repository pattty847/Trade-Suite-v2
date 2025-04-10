 # Dockable Widgets System

This package provides a framework for creating and managing dockable UI widgets in the Trading Suite application.

## Overview

The dockable widgets system allows for creating a customizable trading interface where users can:

- Arrange widgets by dragging and docking them
- Save and load custom layouts
- Create multiple instances of the same widget type
- Receive real-time updates across all widgets

## Key Components

### DockableWidget

Base class for all dockable widgets. Provides common functionality for creating, managing, and docking widgets.

```python
widget = DockableWidget(
    title="My Widget",
    widget_type="my_widget",
    emitter=emitter,
    instance_id="unique_id",
    width=400,
    height=300
)
```

### DashboardManager

Manages dockable widgets and layout persistence.

```python
dashboard = DashboardManager(
    emitter=emitter,
    default_layout_file="config/factory_layout.ini",
    user_layout_file="config/user_layout.ini"
)
```

### Built-in Widgets

- **ChartWidget**: Displays candlestick charts for cryptocurrency trading
- **OrderbookWidget**: Displays and interacts with order book data
- **TradingWidget**: Provides trading functionality, including order entry and position management

## Using the System

### Basic Usage

```python
import dearpygui.dearpygui as dpg
from trade_suite.gui.signals import SignalEmitter
from trade_suite.gui.widgets import DashboardManager, ChartWidget

# Initialize DearPyGUI
dpg.create_context()

# Create signal emitter
emitter = SignalEmitter()

# Create dashboard manager
dashboard = DashboardManager(
    emitter=emitter,
    default_layout_file="config/factory_layout.ini",
    user_layout_file="config/user_layout.ini"
)

# Initialize layout
dashboard.initialize_layout()

# Add a chart widget
dashboard.add_widget(
    "btc_chart",
    ChartWidget(
        emitter,
        "coinbase",
        "BTC/USD",
        "1h"
    )
)

# Create viewport and start the application
dpg.create_viewport(title="Trading Application", width=1280, height=720)
dpg.setup_dearpygui()
dpg.show_viewport()
dpg.start_dearpygui()
dpg.destroy_context()
```

### Running the Demo

To run the demo application:

```bash
python -m trade_suite.gui.widgets.demo
```

Use the `--reset` flag to reset the layout to default:

```bash
python -m trade_suite.gui.widgets.demo --reset
```

### Docking Interactions

- **Drag and drop** widgets to dock them in different positions
- **Hover** near the edges of a window to see docking previews
- **Grab and move** tabs to rearrange them
- **Right-click** on tabs for additional options

## Creating Custom Widgets

To create your own dockable widget:

1. Inherit from `DockableWidget`
2. Implement the required methods:
   - `build_content()`: Build the widget's main content
   - `register_handlers()`: Register event handlers

```python
class MyCustomWidget(DockableWidget):
    def __init__(self, emitter, instance_id=None):
        super().__init__(
            title="My Custom Widget",
            widget_type="custom",
            emitter=emitter,
            instance_id=instance_id
        )
        
    def build_content(self):
        # Build your widget's UI here
        dpg.add_text("Hello from custom widget!")
        
    def register_handlers(self):
        # Register any event handlers
        self.emitter.register(Signals.SOME_SIGNAL, self._on_some_signal)
        
    def _on_some_signal(self, *args, **kwargs):
        # Handle the signal
        pass
```

## Layout Persistence

Layouts are stored in INI files:

- `config/factory_layout.ini`: Default layout shipped with the application
- `config/user_layout.ini`: User's custom layout that persists between sessions

You can:
- Save the current layout as the user layout
- Save the current layout as the default layout
- Reset to the default layout