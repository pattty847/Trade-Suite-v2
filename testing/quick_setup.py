import asyncio
import threading
import dearpygui.dearpygui as dpg

from src.data.data_source import Data
from src.gui import tags
from src.gui.dpg_utils import dpg_help_menu

class ThreadedViewport:
    def __init__(self, loop: asyncio.AbstractEventLoop, data: Data):
        self.loop = loop
        self.data = data

    def start_asyncio_loop(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def fast_setup(fn):
        def wrap(self, *args, **kwargs):
            dpg.create_context()
            fn(self, *args, **kwargs)
            dpg.create_viewport(**kwargs)
            dpg.setup_dearpygui()
            dpg.show_viewport()
            dpg.set_primary_window(tags.PRIMARY_WINDOW, True)
            
            # Start the asyncio loop in a separate thread
            threading.Thread(target=self.start_asyncio_loop, daemon=True).start()
            
            while dpg.is_dearpygui_running():
                dpg.render_dearpygui_frame()
                
            dpg.destroy_context()

        return wrap

    @fast_setup
    def start(self):
        with dpg.window(tag=tags.PRIMARY_WINDOW):
            with dpg.menu_bar(tag=tags.PRIMARY_WINDOW_MENU_BAR):
                dpg_help_menu(tags.PRIMARY_WINDOW_MENU_BAR)

            dpg.add_button(label="Run Async Task", callback=self.trigger_async_task)

    async def async_task(self):
        await asyncio.sleep(5)
        print('test')

    def trigger_async_task(self, sender, app_data, user_data):
        asyncio.run_coroutine_threadsafe(self.async_task(), self.loop)