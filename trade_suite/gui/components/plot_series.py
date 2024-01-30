import dearpygui.dearpygui as dpg

class PlotSeries:
    def __init__(self) -> None:
        pass
    
    def add_series_to_plot(
        self, 
        label, 
        parent, 
        subplot
    ):
        with dpg.plot(label=label, height=-1):
            dpg.add_plot_legend()
            self.xaxis = dpg.add_plot_axis(
                dpg.mvXAxis, time=True
            )
            with dpg.plot_axis(
                dpg.mvYAxis, label="Volume"
            ) as self.yaxis:
                
                pass