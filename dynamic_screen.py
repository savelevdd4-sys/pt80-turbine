import tkinter as tk
from tkinter import ttk, messagebox

import pandas as pd
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

try:
    from dynamic_service import run_dynamic_simulation, list_dynamic_scenarios, build_dynamic_table_for_ui
except Exception:
    run_dynamic_simulation = None
    build_dynamic_table_for_ui = None
    def list_dynamic_scenarios():
        return []

try:
    from main import W_nom
except Exception:
    W_nom = 31500.0

try:
    from environment_models import air_to_water_temp
except Exception:
    def air_to_water_temp(t_air):
        return float(t_air)


class DynamicScreenApp:
    def __init__(self, root: tk.Tk, launcher_root=None):
        self.root = root
        self.launcher_root = launcher_root
        self.root.title('ПТ-80 — Динамический экран')
        self.root.geometry('1600x950')
        self.root.configure(bg='#2b2b2b')

        self.dynamic_result = {}
        self.dynamic_table_df = pd.DataFrame()
        self.dynamic_summary = {}
        self.full_df = pd.DataFrame()

        self.scenarios = list_dynamic_scenarios() if callable(list_dynamic_scenarios) else []
        self.scenario_map = {item['label']: item['key'] for item in self.scenarios if isinstance(item, dict) and 'label' in item and 'key' in item}
        scenario_labels = list(self.scenario_map.keys())

        self.scenario_var = tk.StringVar(value=scenario_labels[0] if scenario_labels else '')
        self.t_end_var = tk.DoubleVar(value=600.0)
        self.n_points_var = tk.IntVar(value=1201)
        self.nz_var = tk.DoubleVar(value=80.0)
        self.gprom_var = tk.DoubleVar(value=0.0)
        self.qtf_var = tk.DoubleVar(value=60.0)
        self.shema_tf_var = tk.IntVar(value=1)
        self.t_air_var = tk.DoubleVar(value=15.0)

        # Вкладки по каждому элементу / узлу схемы
        self.tab_defs = [
            ('overview', 'Обзор', ['N_el_actual', 'Nz_set', 'Ne_load', 'G0', 'P_k', 'delta_balance'], 'Общая целевая функция режима'),
            ('cvd', 'ЦВД', ['G0', 'P1', 'P2', 'P3', 'P_prom'], 'Расход и давления ЦВД'),
            ('csnd', 'ЦСНД', ['G_cond', 'P4', 'P5', 'P6', 'P7', 'P_vto', 'P_nto', 'P_k'], 'Тракт ЦСНД и хвост'),
            ('generator', 'Генератор', ['N_el_actual', 'Nz_set', 'Ne_load', 'omega'], 'Электрическая мощность и скорость ротора'),
            ('condenser', 'Конденсатор', ['G_cond', 'P_k'], 'Расход в конденсатор и вакуум'),
            ('pvd7', 'ПВД-7', ['P1', 'G0'], 'Состояние ПВД-7'),
            ('pvd6', 'ПВД-6', ['P2', 'G0'], 'Состояние ПВД-6'),
            ('pvd5', 'ПВД-5', ['P3', 'G0'], 'Состояние ПВД-5'),
            ('pnd4', 'ПНД-4', ['P4', 'G_cond'], 'Состояние ПНД-4'),
            ('pnd3', 'ПНД-3', ['P5', 'G_cond'], 'Состояние ПНД-3'),
            ('pnd2', 'ПНД-2', ['P6', 'G_cond'], 'Состояние ПНД-2'),
            ('pnd1', 'ПНД-1', ['P7', 'G_cond'], 'Состояние ПНД-1'),
            ('deaerator', 'Деаэратор', ['G0', 'P3', 'P4'], 'Узел деаэратора'),
            ('psg1', 'ПСГ-1 / ВТО', ['G_vto', 'P_vto', 'Qtf'], 'Верхний теплофикационный отбор'),
            ('psg2', 'ПСГ-2 / НТО', ['G_nto', 'P_nto', 'Qtf'], 'Нижний теплофикационный отбор'),
            ('heating', 'Теплофикация', ['G_vto', 'G_nto', 'Qtf', 'N_el_actual'], 'Тепловая часть режима'),
            ('balance', 'Баланс', ['delta_balance', 'G0', 'G_cond', 'G_vto', 'G_nto'], 'Баланс парораспределения'),
        ]
        self.tab_widgets = {}
        self.playback_job = None
        self.playback_index = 0
        self.playback_running = False
        self.playback_speed_ms = 1000
        self.current_view_df = pd.DataFrame()
        self.live_mode = False
        self.live_job = None
        self.live_df = pd.DataFrame()
        self.live_step_index = 0

        self._build_ui()
        self._add_return_button()

    def _add_return_button(self):
        if self.launcher_root is None:
            return
        host = ttk.Frame(self.root)
        host.place(relx=1.0, x=-12, y=8, anchor='ne')
        ttk.Button(host, text='Вернуться', command=self.return_to_launcher).pack()

    def return_to_launcher(self):
        try:
            self.pause_live_calculation()
            self.pause_playback()
            self.root.destroy()
        finally:
            if self.launcher_root is not None:
                try:
                    self.launcher_root.deiconify()
                    self.launcher_root.lift()
                    self.launcher_root.focus_force()
                except Exception:
                    pass


    def _apply_limits_to_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        if not isinstance(df, pd.DataFrame) or df.empty:
            return df
        out = df.copy()
        if 'N_el_actual' in out.columns:
            if 'Nz_set' in out.columns:
                out['N_el_actual'] = out[['N_el_actual', 'Nz_set']].min(axis=1)
            else:
                out['N_el_actual'] = out['N_el_actual'].clip(upper=float(self.nz_var.get()))
        if 'Ne_load' in out.columns and 'Nz_set' in out.columns:
            out['Ne_load'] = out[['Ne_load', 'Nz_set']].min(axis=1)
        return out

    def _channel_unit(self, channel: str) -> str:
        if channel in {'N_el_actual', 'Nz_set', 'Ne_load', 'Qtf'}:
            return 'power'
        if channel in {'G0', 'G_cond', 'G_vto', 'G_nto', 'delta_balance'}:
            return 'flow'
        if channel in {'P1', 'P2', 'P3', 'P4', 'P5', 'P6', 'P7', 'P_prom', 'P_vto', 'P_nto', 'P_k'}:
            return 'pressure'
        if channel in {'omega'}:
            return 'rotor'
        return 'other'

    def _unit_ylabel(self, unit_key: str) -> str:
        return {
            'power': 'Мощность / нагрузка',
            'flow': 'Расход / баланс',
            'pressure': 'Давление',
            'rotor': 'Скорость ротора',
            'other': 'Значение',
        }.get(unit_key, 'Значение')


    def _stop_playback_job(self):
        if self.playback_job is not None:
            try:
                self.root.after_cancel(self.playback_job)
            except Exception:
                pass
            self.playback_job = None

    def pause_playback(self):
        self.playback_running = False
        self._stop_playback_job()

    def start_playback(self):
        df = self._active_df()
        if not isinstance(df, pd.DataFrame) or df.empty:
            messagebox.showinfo('Нет данных', 'Сначала запусти динамический расчёт.')
            return
        try:
            self.playback_speed_ms = max(50, int(self.playback_speed_var.get()))
        except Exception:
            self.playback_speed_ms = 1000
            self.playback_speed_var.set(1000)
        self.playback_running = True
        if self.playback_index >= len(df):
            self.playback_index = 0
        self._stop_playback_job()
        self._playback_step()

    def _playback_step(self):
        df = self.full_df if isinstance(self.full_df, pd.DataFrame) and not self.full_df.empty else self.dynamic_table_df
        if not self.playback_running or not isinstance(df, pd.DataFrame) or df.empty:
            self._stop_playback_job()
            return
        end_idx = min(self.playback_index + 1, len(df))
        self.current_view_df = df.iloc[:end_idx].copy()
        self.update_table()
        self.update_all_tabs()
        self.playback_index = end_idx
        if self.playback_index < len(df):
            self.playback_job = self.root.after(self.playback_speed_ms, self._playback_step)
        else:
            self.playback_running = False
            self.playback_job = None

    def _active_df(self):
        if isinstance(self.current_view_df, pd.DataFrame) and not self.current_view_df.empty:
            return self.current_view_df
        return self.dynamic_table_df


    def _stop_live_job(self):
        if self.live_job is not None:
            try:
                self.root.after_cancel(self.live_job)
            except Exception:
                pass
            self.live_job = None

    def pause_live_calculation(self):
        self.live_mode = False
        self.playback_running = False
        self._stop_live_job()
        self._stop_playback_job()

    def start_live_calculation(self):
        df = self.full_df if isinstance(self.full_df, pd.DataFrame) and not self.full_df.empty else self.dynamic_table_df
        if not isinstance(df, pd.DataFrame) or df.empty:
            messagebox.showinfo('Нет данных', 'Сначала запусти динамический расчёт.')
            return
        try:
            self.playback_speed_ms = max(50, int(self.playback_speed_var.get()))
        except Exception:
            self.playback_speed_ms = 1000
            self.playback_speed_var.set(1000)

        self.pause_live_calculation()
        self.live_mode = True
        self.live_step_index = 0
        self.live_df = df.copy()
        self.current_view_df = self.live_df.iloc[:0].copy()
        self.update_table()
        self.update_all_tabs()
        self._live_calculation_step()

    def _live_calculation_step(self):
        if not self.live_mode or not isinstance(self.live_df, pd.DataFrame) or self.live_df.empty:
            self._stop_live_job()
            return

        end_idx = min(self.live_step_index + 1, len(self.live_df))
        self.current_view_df = self.live_df.iloc[:end_idx].copy()
        self.update_table()
        self.update_all_tabs()

        self.live_step_index = end_idx
        if self.live_step_index < len(self.live_df):
            self.live_job = self.root.after(self.playback_speed_ms, self._live_calculation_step)
        else:
            self.live_mode = False
            self.live_job = None

    def _build_ui(self):
        outer = ttk.Frame(self.root, padding=8)
        outer.pack(fill='both', expand=True)
        outer.columnconfigure(0, weight=0)
        outer.columnconfigure(1, weight=1)
        outer.rowconfigure(0, weight=1)

        left = ttk.LabelFrame(outer, text='Параметры', padding=8)
        left.grid(row=0, column=0, sticky='nsw', padx=(0, 8))
        for i in range(20):
            left.rowconfigure(i, weight=0)
        left.columnconfigure(1, weight=1)

        row = 0
        ttk.Label(left, text='Сценарий').grid(row=row, column=0, sticky='w', pady=2)
        self.scenario_combo = ttk.Combobox(left, textvariable=self.scenario_var, state='readonly', values=list(self.scenario_map.keys()), width=28)
        self.scenario_combo.grid(row=row, column=1, sticky='ew', pady=2)
        row += 1

        for label, var in [
            ('Горизонт, с', self.t_end_var),
            ('Точек', self.n_points_var),
            ('Nz, МВт', self.nz_var),
            ('Gпром, т/ч', self.gprom_var),
            ('Qтф, Гкал/ч', self.qtf_var),
            ('Схема ТФ', self.shema_tf_var),
            ('T воздуха, °C', self.t_air_var),
        ]:
            ttk.Label(left, text=label).grid(row=row, column=0, sticky='w', pady=2)
            ttk.Entry(left, textvariable=var, width=14).grid(row=row, column=1, sticky='ew', pady=2)
            row += 1

        ttk.Button(left, text='Начать расчёт', command=self.start_calculation_and_live).grid(row=row, column=0, columnspan=2, sticky='ew', pady=(8, 6))
        row += 1

        playback_bar = ttk.Frame(left)
        playback_bar.grid(row=row, column=0, columnspan=2, sticky='ew', pady=(0, 8))
        playback_bar.columnconfigure(2, weight=1)

        ttk.Button(playback_bar, text='Пауза', command=self.pause_live_calculation).grid(row=0, column=0, padx=(0, 4))
        ttk.Label(playback_bar, text='Шаг, мс').grid(row=0, column=1, sticky='e', padx=(8, 4))
        self.playback_speed_var = tk.IntVar(value=1000)
        ttk.Entry(playback_bar, textvariable=self.playback_speed_var, width=8).grid(row=0, column=2, sticky='e')
        row += 1

        ttk.Label(left, text='Сводка').grid(row=row, column=0, columnspan=2, sticky='w', pady=(8, 4))
        row += 1
        self.summary_text = tk.Text(left, height=16, width=38, wrap='word')
        self.summary_text.grid(row=row, column=0, columnspan=2, sticky='nsew')
        left.rowconfigure(row, weight=1)

        right = ttk.Frame(outer)
        right.grid(row=0, column=1, sticky='nsew')
        right.rowconfigure(0, weight=1)
        right.columnconfigure(0, weight=1)

        notebook_box = ttk.LabelFrame(right, text='Динамика по элементам схемы', padding=4)
        notebook_box.grid(row=0, column=0, sticky='nsew')
        notebook_box.rowconfigure(0, weight=1)
        notebook_box.columnconfigure(0, weight=1)

        self.notebook = ttk.Notebook(notebook_box)
        self.notebook.grid(row=0, column=0, sticky='nsew')

        for tab_key, tab_title, channels, target_label in self.tab_defs:
            frame = ttk.Frame(self.notebook, padding=4)
            frame.rowconfigure(1, weight=3)
            frame.rowconfigure(3, weight=2)
            frame.columnconfigure(0, weight=1)

            info = ttk.Label(frame, text=f'Тренд целевой функции / ключевых каналов: {target_label}')
            info.grid(row=0, column=0, sticky='w', pady=(0, 4))

            fig = Figure(figsize=(9.5, 4.2), dpi=100)
            ax = fig.add_subplot(111)
            canvas = FigureCanvasTkAgg(fig, master=frame)
            canvas.get_tk_widget().grid(row=1, column=0, sticky='nsew', pady=(0, 6))

            table_label = ttk.Label(frame, text='Таблица по вкладке')
            table_label.grid(row=2, column=0, sticky='w', pady=(0, 4))

            table_host = ttk.Frame(frame)
            table_host.grid(row=3, column=0, sticky='nsew')
            table_host.rowconfigure(0, weight=1)
            table_host.columnconfigure(0, weight=1)

            table_columns = ('t', *channels)
            tree = ttk.Treeview(table_host, columns=table_columns, show='headings', height=8)
            for c in table_columns:
                tree.heading(c, text=c)
                width = 95 if c == 't' else 120
                tree.column(c, width=width, anchor='center', stretch=True)
            tree.grid(row=0, column=0, sticky='nsew')

            ybar = ttk.Scrollbar(table_host, orient='vertical', command=tree.yview)
            xbar = ttk.Scrollbar(table_host, orient='horizontal', command=tree.xview)
            tree.configure(yscrollcommand=ybar.set, xscrollcommand=xbar.set)
            ybar.grid(row=0, column=1, sticky='ns')
            xbar.grid(row=1, column=0, sticky='ew')

            self.tab_widgets[tab_key] = {
                'frame': frame,
                'fig': fig,
                'ax': ax,
                'canvas': canvas,
                'channels': channels,
                'target_label': target_label,
                'title': tab_title,
                'tree': tree,
                'table_columns': table_columns,
            }
            self._style_axes(ax, tab_title)

            self.notebook.add(frame, text=tab_title)

        self._show_empty()

    def _style_axes(self, ax, title: str):
        fig = ax.figure
        fig.patch.set_facecolor('#202124')
        ax.set_facecolor('#202124')
        ax.grid(True, color='#5f6368', alpha=0.45)
        ax.tick_params(colors='#e8eaed')
        for spine in ax.spines.values():
            spine.set_color('#9aa0a6')
        ax.set_xlabel('Время, с', color='#e8eaed')
        ax.set_ylabel('Значение', color='#e8eaed')
        ax.set_title(title, color='#e8eaed')

    def _build_base_mode(self):
        return {
            'mode_id': 'GUI-DYNAMIC-SCREEN',
            'Nz': float(self.nz_var.get()),
            'Gprom': float(self.gprom_var.get()),
            'Qtf': float(self.qtf_var.get()),
            'shema_tf': int(self.shema_tf_var.get()),
            'W_cw': float(W_nom),
            'tw1': float(air_to_water_temp(float(self.t_air_var.get()))),
            'tech_state_coeff': 1.0,
            'component_health': {},
            'N_e': float(self.nz_var.get()),
        }

    def _selected_scenario_key(self):
        label = self.scenario_var.get().strip()
        return self.scenario_map.get(label, label)

    def start_calculation_and_live(self):
        self.run_simulation(auto_start_live=True)

    def run_simulation(self, auto_start_live=False):
        if run_dynamic_simulation is None:
            messagebox.showerror('Динамика недоступна', 'Не найден модуль dynamic_service.py')
            return
        try:
            t_end = float(self.t_end_var.get())
            n_points = int(self.n_points_var.get())
            if t_end <= 0 or n_points < 10:
                raise ValueError('Горизонт должен быть > 0, а число точек не меньше 10.')
            result = run_dynamic_simulation(
                scenario_name=self._selected_scenario_key(),
                t_end=t_end,
                n_points=n_points,
                base_mode=self._build_base_mode(),
            )
            if isinstance(result, dict) and result.get('error'):
                raise RuntimeError(str(result.get('error')))
            self.dynamic_result = result if isinstance(result, dict) else {}

            table_df = pd.DataFrame()
            if callable(build_dynamic_table_for_ui):
                table_df = build_dynamic_table_for_ui(self.dynamic_result)
            elif isinstance(self.dynamic_result.get('table'), pd.DataFrame):
                table_df = self.dynamic_result['table']
            self.dynamic_table_df = self._apply_limits_to_dataframe(table_df if isinstance(table_df, pd.DataFrame) else pd.DataFrame())

            full_df = self.dynamic_result.get('table_full')
            full_df = full_df if isinstance(full_df, pd.DataFrame) else self.dynamic_table_df.copy()
            self.full_df = self._apply_limits_to_dataframe(full_df)
            self.dynamic_summary = self.dynamic_result.get('summary', {}) if isinstance(self.dynamic_result, dict) else {}
            self.pause_live_calculation()
            self.pause_playback()
            self.playback_index = 0
            self.live_step_index = 0
            self.current_view_df = pd.DataFrame()
            self.live_df = pd.DataFrame()
            self.update_summary()
            if auto_start_live:
                self.current_view_df = pd.DataFrame()
                self.update_table()
                self.update_all_tabs()
                self.start_live_calculation()
            else:
                self.update_table()
                self.update_all_tabs()
        except Exception as e:
            messagebox.showerror('Ошибка динамического расчёта', str(e))

    def update_summary(self):
        self.summary_text.delete('1.0', 'end')
        s = self.dynamic_summary or {}
        if not s:
            self.summary_text.insert('1.0', 'Нет данных динамического расчёта.\nНажми «Начать расчёт», чтобы расчёт шёл постепенно, а графики строились во времени.')
            return
        ini = s.get('initial', {})
        fin = s.get('final', {})
        mx = s.get('maxima', {})
        lines = [
            f"Сценарий: {s.get('scenario_label', s.get('scenario', '—'))}",
            f"Длительность: {s.get('duration_s', 0.0):.1f} с",
            '',
            f"Начало: N={ini.get('power_mw', 0.0):.2f} МВт; G0={ini.get('g0_tph', 0.0):.2f} т/ч; Pк={ini.get('pk_kpa', 0.0):.2f} кПа",
            f"Конец: N={min(fin.get('power_mw', 0.0), fin.get('setpoint_mw', fin.get('power_mw', 0.0))):.2f} МВт; G0={fin.get('g0_tph', 0.0):.2f} т/ч; Pк={fin.get('pk_kpa', 0.0):.2f} кПа",
            '',
            f"Макс. мощность: {mx.get('max_power_mw', 0.0):.2f} МВт",
            f"Макс. G0: {mx.get('max_g0_tph', 0.0):.2f} т/ч",
            f"Макс. Pк: {mx.get('max_pk_kpa', 0.0):.2f} кПа",
            f"Макс. невязка: {mx.get('max_balance_error_tph', 0.0):.3f} т/ч",
        ]
        self.summary_text.insert('1.0', '\n'.join(lines))

    def _format_table_value(self, val):
        if pd.isna(val):
            return ''
        if isinstance(val, (int, float)):
            return f'{float(val):.4f}'
        return str(val)

    def _update_tab_table(self, tab_key: str):
        widget = self.tab_widgets[tab_key]
        tree = widget['tree']
        for iid in tree.get_children():
            tree.delete(iid)

        df = self._active_df()
        if not isinstance(df, pd.DataFrame) or df.empty:
            return

        cols = list(widget['table_columns'])
        for _, row in df.iterrows():
            values = [self._format_table_value(row[c] if c in df.columns else '') for c in cols]
            tree.insert('', 'end', values=values)

    def update_table(self):
        for tab_key in self.tab_widgets:
            self._update_tab_table(tab_key)

    def _plot_tab(self, tab_key: str):
        widget = self.tab_widgets[tab_key]
        fig = widget['fig']
        fig.clf()

        df = self._active_df()
        is_waiting_for_fill = (self.live_mode or self.playback_running) and (
            not isinstance(df, pd.DataFrame) or df.empty
        )

        if not isinstance(df, pd.DataFrame) or df.empty or 't' not in df.columns:
            ax = fig.add_subplot(111)
            self._style_axes(ax, widget['title'])
            empty_text = 'Ожидание заполнения таблицы…' if is_waiting_for_fill else 'Нажми «Начать расчёт» для пошагового построения'
            ax.text(0.5, 0.5, empty_text, color='#e8eaed', ha='center', va='center', transform=ax.transAxes)
            widget['ax'] = ax
            widget['canvas'].draw_idle()
            return

        groups = {}
        for channel in widget['channels']:
            if channel in df.columns:
                groups.setdefault(self._channel_unit(channel), []).append(channel)

        if not groups:
            ax = fig.add_subplot(111)
            self._style_axes(ax, widget['title'])
            ax.text(0.5, 0.5, 'Для этого элемента нет каналов в текущем расчёте', color='#e8eaed', ha='center', va='center', transform=ax.transAxes)
            widget['ax'] = ax
            widget['canvas'].draw_idle()
            return

        axes = []
        unit_keys = [k for k in ['power', 'flow', 'pressure', 'rotor', 'other'] if k in groups]
        current_t = None
        try:
            current_t = float(df['t'].iloc[-1])
        except Exception:
            current_t = None

        for idx, unit_key in enumerate(unit_keys, start=1):
            ax = fig.add_subplot(len(unit_keys), 1, idx)
            self._style_axes(ax, widget['title'] if idx == 1 else '')
            if idx != len(unit_keys):
                ax.set_xlabel('', color='#e8eaed')
            ax.set_ylabel(self._unit_ylabel(unit_key), color='#e8eaed')

            for channel in groups[unit_key]:
                ax.plot(df['t'], df[channel], label=channel)
                if len(df) == 1:
                    ax.scatter(df['t'].iloc[-1], df[channel].iloc[-1], s=24)

            if current_t is not None:
                ax.axvline(current_t, linestyle='--', alpha=0.35)

            leg = ax.legend(facecolor='#202124', edgecolor='#9aa0a6', loc='best')
            for txt in leg.get_texts():
                txt.set_color('#e8eaed')
            axes.append(ax)

        fig.tight_layout()
        widget['ax'] = axes[0]
        widget['canvas'].draw_idle()

    def update_all_tabs(self):
        for tab_key in self.tab_widgets:
            self._plot_tab(tab_key)

    def _show_empty(self):
        self.summary_text.delete('1.0', 'end')
        self.summary_text.insert('1.0', 'Нет данных динамического расчёта.')
        self.update_table()
        self.update_all_tabs()


if __name__ == '__main__':
    root = tk.Tk()
    app = DynamicScreenApp(root)
    root.mainloop()
