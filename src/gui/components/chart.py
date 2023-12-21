import asyncio
import dearpygui.dearpygui as dpg
from src.data.data_source import Data
from src.gui.signals import SignalEmitter, Signals
from src.gui.task_manager import TaskManager

class Chart:
    def __init__(self, emitter: SignalEmitter, data: Data, task_manager: TaskManager) -> None:
        self.tag = dpg.generate_uuid()
        self.emitter = emitter
        self.data = data
        self.task_manager = task_manager

        self.emitter.register(Signals.VIEWPORT_RESIZED, self.resize_window)
        self.emitter.register(Signals.NEW_TRADE, self.on_new_trade)
        
        initial_width = 500
        initial_height = 500
        
        dpg.add_button(label="Run Async Task", callback=self.trigger_async_task)
        dpg.add_button(label="Stop Async Task", callback=self.stop_async_task)
        dpg.add_text(tag='price')
        dpg.add_text(tag='cost')

        with dpg.plot(label=f'{self.data.exchanges[0]}', tag=self.tag, width=initial_width, height=initial_height):
            dpg.add_plot_legend()
            
            dpg.add_plot_axis(dpg.mvXAxis, label="X")
            dpg.add_plot_axis(dpg.mvYAxis, label="Y", tag="y_axis")
            
            dpg.add_line_series([0.1, 0.2, 0.3], [0.1, 0.2, 0.3], label="0.5 + 0.5 * sin(x)", parent="y_axis", tag="series_tag")

        # Store the initial ratio of the window to the viewport
        self.initial_ratio = (
            initial_width / dpg.get_viewport_width(),
            initial_height / dpg.get_viewport_height()
        )

    async def async_task(self):
        await self.data.stream_trades(['BTC/USD'], tag='results')

    def trigger_async_task(self, sender, app_data, user_data):
        self.task_manager.start_task("async_task", self.async_task())

    def stop_async_task(self, sender, app_data, user_data):
        self.task_manager.stop_task("async_task")

    # Optionally, a method to stop all tasks
    def stop_all_async_tasks(self):
        self.task_manager.stop_all_tasks()

    def resize_window(self, width, height):
        # Use the stored initial ratio to calculate new dimensions
        new_width = width * self.initial_ratio[0]
        new_height = height * self.initial_ratio[1]
        dpg.configure_item(self.tag, width=int(new_width), height=int(new_height))

    def on_new_trade(self, trade_data):
        # Update the UI elements
        dpg.set_value('price', trade_data['price'])
        # Update other UI elements as needed
        dpg.set_value('cost', trade_data['cost'])