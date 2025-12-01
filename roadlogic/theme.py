# See: https://github.com/zauberzeug/nicegui/blob/main/examples/modularization/theme.py
from contextlib import contextmanager

# from menu import menu

from nicegui import ui


@contextmanager
def frame(navigation_title: str):
    """Custom page frame to share the same styling and behavior across all pages"""
    ui.colors(primary='#6E93D6', secondary='#53B689', accent='#111B1E', positive='#53B689')
    with ui.header():
        ui.button('RoadLogic', on_click=lambda: ui.navigate.to("/")).classes('font-bold')
        ui.label(navigation_title).classes('text-h5')
        ui.space()

    # Ensure that whatever we create as page will be one single column centered on the screen
    # with ui.column().classes('absolute-center items-center w-full').style("margin: 20px"):
    with ui.column().classes('absolute-center w-full margin-20'):
        yield