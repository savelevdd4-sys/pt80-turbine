from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from main_gui import PT80App


class DynamicPT80App(PT80App):
    """Первый шаг по разделению режимов: используем существующую динамическую вкладку,
    но запускаем её как отдельный режим приложения."""

    def __init__(self, root: tk.Tk):
        super().__init__(root)
        self.root.title("ПТ-80 — динамический режим")
        self._focus_dynamic_mode()

    def _focus_dynamic_mode(self) -> None:
        try:
            dynamic_index = self.notebook.index(self.dynamic_tab)
            self.notebook.select(dynamic_index)
        except Exception:
            pass
