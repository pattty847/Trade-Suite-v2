import dearpygui.dearpygui as dpg

from src.gui.signals import Signals, SignalEmitter


class Window:
    def __init__(self, emitter: SignalEmitter) -> None:
        self.emitter = emitter
        self.emitter.register(Signals.SELECT_EXCHANGE, self.update_text)

        with dpg.window(label="test"):
            dpg.add_text("", tag="test")

    def update_text(self, exchange, *args):
        dpg.configure_item("test", default_value=f"{exchange}")
        print(*args)
