"""Sizes for ttk tables shown inside CustomTkinter screens.

A ttk table takes sizes in screen pixels and does not follow the Windows display scale, while
CustomTkinter widgets do: at 200% its text was a third smaller than the buttons around it.
Multiply by the screen's CustomTkinter scale (``widget._get_widget_scaling()``) instead.
"""
from tkinter import ttk

TABLE_FONT_SIZE = 11  # same size as the text of the CustomTkinter widgets around the tables
TABLE_ROW_HEIGHT = 26


def table_font(scale, *styles):
    return ("Segoe UI", -round(TABLE_FONT_SIZE * scale), *styles)


def style_table(widget, style_name, scale):
    style = ttk.Style(widget)
    style.configure(style_name, rowheight=round(TABLE_ROW_HEIGHT * scale), font=table_font(scale))
    style.configure(f"{style_name}.Heading", font=table_font(scale, "bold"))
