# import dearpygui.dearpygui as dpg


# def print_me(sender):
#     print(f"Menu Item: {sender}")


# dpg.create_context()
# dpg.create_viewport(title="Custom Title", width=600, height=200)

# with dpg.viewport_menu_bar():
#     with dpg.menu(label="File"):
#         dpg.add_menu_item(label="Save", callback=print_me)
#         dpg.add_menu_item(label="Save As", callback=print_me)

#         with dpg.menu(label="Settings"):
#             dpg.add_menu_item(label="Setting 1", callback=print_me, check=True)
#             dpg.add_menu_item(label="Setting 2", callback=print_me)

#     dpg.add_menu_item(label="Help", callback=print_me)

#     with dpg.menu(label="Widget Items"):
#         dpg.add_checkbox(label="Pick Me", callback=print_me)
#         dpg.add_button(label="Press Me", callback=print_me)
#         dpg.add_color_picker(label="Color Me", callback=print_me)

# dpg.setup_dearpygui()
# dpg.show_viewport()
# dpg.start_dearpygui()
# dpg.destroy_context()


import http.client
import json

conn = http.client.HTTPSConnection("api.exchange.coinbase.com")
headers = {"Content-Type": "application/json"}

try:
    conn.request("GET", "/products", "", headers)
    res = conn.getresponse()

    # Check if the response is successful
    if res.status == 200:
        data = res.read()
        products = data.decode("utf-8")
        print(products)
    else:
        print(f"Error: {res.status}, {res.reason}")

except Exception as e:
    print(f"An error occurred: {e}")

finally:
    conn.close()
