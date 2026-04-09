from __future__ import annotations

import tkinter as tk
from tkinter import ttk, messagebox

from main_gui import PT80App

try:
    from dynamic_screen import DynamicScreenApp
    _dynamic_error = None
except Exception as exc:
    DynamicScreenApp = None
    _dynamic_error = str(exc)


class ModeLauncher:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title('ПТ-80 — выбор режима')
        self.root.geometry('620x300')
        self.root.minsize(620, 300)
        self._build_ui()

    def _build_ui(self) -> None:
        frame = ttk.Frame(self.root, padding=20)
        frame.pack(fill='both', expand=True)

        ttk.Label(
            frame,
            text='Выберите режим работы',
            font=('Arial', 16, 'bold')
        ).pack(pady=(10, 22))

        ttk.Button(
            frame,
            text='Статический расчёт',
            command=self.open_static
        ).pack(fill='x', pady=8, ipady=14)

        ttk.Button(
            frame,
            text='Динамический экран',
            command=self.open_dynamic
        ).pack(fill='x', pady=8, ipady=14)

    def _return_to_launcher(self, mode_window: tk.Toplevel) -> None:
        try:
            mode_window.destroy()
        finally:
            self.root.deiconify()
            self.root.lift()
            try:
                self.root.focus_force()
            except Exception:
                pass

    def _decorate_mode_window(self, mode_window: tk.Toplevel, title: str) -> None:
        mode_window.title(title)

        topbar = ttk.Frame(mode_window)
        topbar.place(relx=1.0, x=-12, y=8, anchor='ne')

        ttk.Button(
            topbar,
            text='Вернуться',
            command=lambda w=mode_window: self._return_to_launcher(w)
        ).pack()

        mode_window.protocol('WM_DELETE_WINDOW', lambda w=mode_window: self._return_to_launcher(w))

    def _open_mode(self, app_cls, title: str) -> None:
        self.root.withdraw()
        mode_window = tk.Toplevel(self.root)
        self._decorate_mode_window(mode_window, title)
        app_cls(mode_window)

    def open_static(self) -> None:
        self._open_mode(PT80App, 'ПТ-80 — Статический расчёт')

    def open_dynamic(self) -> None:
        if DynamicScreenApp is None:
            messagebox.showerror('Ошибка запуска динамики', _dynamic_error or 'dynamic_screen.py не найден')
            return
        self._open_mode(DynamicScreenApp, 'ПТ-80 — Динамический экран')


if __name__ == '__main__':
    root = tk.Tk()
    ModeLauncher(root)
    root.mainloop()
