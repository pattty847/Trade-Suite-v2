from collections import deque
import dearpygui.dearpygui as dpg

class Console:
    def __init__(self) -> None:
        self.log_ = deque(maxlen=10000)