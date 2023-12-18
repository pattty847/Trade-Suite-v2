import dearpygui.dearpygui as dpg

class State:
    def __init__(self):
        # Initialize your state variables
        self.active_tab = None
        self.user_data = {}
        # Add more state variables as needed

    # Methods to update state
    def set_active_tab(self, tab):
        self.active_tab = tab

    def update_user_data(self, data):
        self.user_data.update(data)

    # Methods to access state
    def get_active_tab(self):
        return self.active_tab

    def get_user_data(self):
        return self.user_data
