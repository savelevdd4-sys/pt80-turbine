from __future__ import annotations

import math
import tkinter as tk
from tkinter import ttk, messagebox
from typing import Any, Dict, List, Optional

import matplotlib
matplotlib.use('TkAgg')
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

from block_registry import STATIC_BLOCKS
from calc_service import run_mode_calculation
from economics import calculate_economics_from_results
from formula_report import build_human_formula_report
from steam_balance import calculate_station_steam_balance
from turbine_limits import evaluate_limits


class StaticPT80App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("ПТ-80 — статический режим")
        self.root.geometry("1380x860")
        self.results: Optional[Dict[str, Any]] = None
        self.eco: Optional[Dict[str, Any]] = None
        self.balance: Optional[Dict[str, Any]] = None
        self.limits: Optional[Dict[str, Any]] = None
        self.block_pages: Dict[str, Dict[str, Any]] = {}
        self._build_vars()
        self._build_ui()

    def _build_vars(self) -> None:
        self.vars = {
            'Nz': tk.DoubleVar(value=80.0),
            'Gprom': tk.DoubleVar(value=0.0),
            'Qtf': tk.DoubleVar(value=60.0),
            'shema_tf': tk.IntVar(value=1),
            't_air': tk.DoubleVar(value=15.0),
            'fuel_price': tk.DoubleVar(value=6000.0),
            'market_price': tk.DoubleVar(value=2500.0),
            'tech_limit_mw': tk.DoubleVar(value=100.0),
            'fresh_steam_temp': tk.DoubleVar(value=555.0),
            't_water_in': tk.DoubleVar(value=50.0),
            'G_water_psg': tk.DoubleVar(value=0.0),
        }

    def _build_ui(self) -> None:
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill='both', expand=True, padx=6, pady=6)

        self.page_input = ttk.Frame(self.notebook)
        self.notebook.add(self.page_input, text="1. Задатчик НУ")
        self._build_input_page()

        self.page_summary = ttk.Frame(self.notebook)
        self.notebook.add(self.page_summary, text="2. Общие результаты")
        self._build_summary_page()

        for idx, block in enumerate(STATIC_BLOCKS, start=3):
            frame = ttk.Frame(self.notebook)
            self.notebook.add(frame, text=f"{idx}. {block.title}")
            self._build_block_page(frame, block.key, block.title, block.short_theory)

        self.page_formulas = ttk.Frame(self.notebook)
        self.notebook.add(self.page_formulas, text=f"{len(STATIC_BLOCKS)+3}. Формулы")
        self._build_formulas_page()

    def _build_input_page(self) -> None:
        outer = ttk.Frame(self.page_input, padding=10)
        outer.pack(fill='both', expand=True)
        outer.columnconfigure(0, weight=3)
        outer.columnconfigure(1, weight=2)
        outer.rowconfigure(0, weight=1)

        form = ttk.LabelFrame(outer, text="Начальные условия", padding=10)
        form.grid(row=0, column=0, sticky='nsew', padx=(0, 8))
        form.columnconfigure(1, weight=1)

        fields = [
            ("Целевая электрическая мощность, МВт", 'Nz'),
            ("Производственный отбор, т/ч", 'Gprom'),
            ("Тепловая нагрузка, Гкал/ч", 'Qtf'),
            ("Схема теплофикации (1/2)", 'shema_tf'),
            ("Температура воздуха, °C", 't_air'),
            ("Температура сетевой воды на входе в ПСГ, °C", 't_water_in'),
            ("Расход сетевой воды, т/ч (0 = авто)", 'G_water_psg'),
            ("Цена топлива, руб/т у.т.", 'fuel_price'),
            ("Цена рынка, руб/МВт·ч", 'market_price'),
            ("Технический предел мощности, МВт", 'tech_limit_mw'),
            ("Температура свежего пара, °C", 'fresh_steam_temp'),
        ]
        for row, (label, key) in enumerate(fields):
            ttk.Label(form, text=label).grid(row=row, column=0, sticky='w', padx=(0, 8), pady=4)
            ttk.Entry(form, textvariable=self.vars[key], width=16).grid(row=row, column=1, sticky='ew', pady=4)

        actions = ttk.Frame(form)
        actions.grid(row=len(fields), column=0, columnspan=2, sticky='ew', pady=(12, 0))
        ttk.Button(actions, text="Выполнить расчёт", command=self.run_calculation).pack(side='left')
        ttk.Button(actions, text="Открыть формулы", command=lambda: self.notebook.select(self.page_formulas)).pack(side='left', padx=6)

        note = ttk.Label(
            form,
            text=(
                "На этой странице задаётся исходный режим. В этой версии параметры ПСГ уже "
                "передаются в стационарное ядро: температура воды на входе и, при наличии, "
                "расход сетевой воды."
            ),
            wraplength=560,
            justify='left'
        )
        note.grid(row=len(fields)+1, column=0, columnspan=2, sticky='w', pady=(12, 0))

        scheme = ttk.LabelFrame(outer, text="Общая схема и структура страниц", padding=10)
        scheme.grid(row=0, column=1, sticky='nsew')
        scheme.columnconfigure(0, weight=1)
        ttk.Label(
            scheme,
            text=(
                "Статика:\n"
                "1. Задатчик НУ\n"
                "2. Общие результаты\n"
                "3…N. Страницы отдельных элементов\n"
                "Последняя. Человеческие формулы расчёта\n\n"
                "Доступные блоки уже заведены в реестр и могут уточняться независимо от GUI."
            ),
            justify='left',
            wraplength=360,
        ).grid(row=0, column=0, sticky='nw')

        self.scheme_list = tk.Text(scheme, height=24, wrap='word')
        self.scheme_list.grid(row=1, column=0, sticky='nsew', pady=(8, 0))
        self.scheme_list.insert('1.0', '\n'.join(f"• {idx+3}. {block.title}" for idx, block in enumerate(STATIC_BLOCKS)))
        self.scheme_list.config(state='disabled')

    def _build_summary_page(self) -> None:
        outer = ttk.Frame(self.page_summary, padding=10)
        outer.pack(fill='both', expand=True)
        outer.columnconfigure(0, weight=1)
        outer.columnconfigure(1, weight=1)
        outer.rowconfigure(1, weight=1)

        self.summary_tree = ttk.Treeview(outer, columns=('value', 'unit'), show='tree headings', height=16)
        self.summary_tree.heading('#0', text='Показатель')
        self.summary_tree.heading('value', text='Значение')
        self.summary_tree.heading('unit', text='Ед.')
        self.summary_tree.column('#0', width=340)
        self.summary_tree.column('value', width=130, anchor='e')
        self.summary_tree.column('unit', width=90, anchor='center')
        self.summary_tree.grid(row=0, column=0, sticky='nsew', padx=(0, 8))

        self.summary_text = tk.Text(outer, wrap='word', height=16)
        self.summary_text.grid(row=0, column=1, sticky='nsew')
        self.summary_text.insert('1.0', 'После расчёта здесь появятся итог, экономика, ограничения и короткий вывод.')
        self.summary_text.config(state='disabled')

        self.summary_chart_frame = ttk.LabelFrame(outer, text='Ключевые показатели', padding=6)
        self.summary_chart_frame.grid(row=1, column=0, columnspan=2, sticky='nsew', pady=(8, 0))

    def _build_block_page(self, parent: ttk.Frame, key: str, title: str, theory: str) -> None:
        outer = ttk.Frame(parent, padding=10)
        outer.pack(fill='both', expand=True)
        outer.columnconfigure(0, weight=3)
        outer.columnconfigure(1, weight=2)
        outer.rowconfigure(1, weight=1)

        theory_box = ttk.LabelFrame(outer, text=f"{title}: краткая теория", padding=8)
        theory_box.grid(row=0, column=0, columnspan=2, sticky='ew')
        ttk.Label(theory_box, text=theory, wraplength=1200, justify='left').pack(fill='x')

        table_box = ttk.LabelFrame(outer, text='Таблица параметров', padding=8)
        table_box.grid(row=1, column=0, sticky='nsew', padx=(0, 8), pady=(8, 0))
        table_box.rowconfigure(0, weight=1)
        table_box.columnconfigure(0, weight=1)
        tree = ttk.Treeview(table_box, columns=('value', 'unit'), show='tree headings')
        tree.heading('#0', text='Параметр')
        tree.heading('value', text='Значение')
        tree.heading('unit', text='Ед.')
        tree.column('#0', width=360)
        tree.column('value', width=120, anchor='e')
        tree.column('unit', width=80, anchor='center')
        tree.grid(row=0, column=0, sticky='nsew')
        scroll = ttk.Scrollbar(table_box, orient='vertical', command=tree.yview)
        scroll.grid(row=0, column=1, sticky='ns')
        tree.configure(yscrollcommand=scroll.set)

        chart_box = ttk.LabelFrame(outer, text='Графики блока', padding=8)
        chart_box.grid(row=1, column=1, sticky='nsew', pady=(8, 0))
        chart_box.rowconfigure(0, weight=1)
        chart_box.columnconfigure(0, weight=1)

        self.block_pages[key] = {
            'tree': tree,
            'chart_frame': chart_box,
        }

    def _build_formulas_page(self) -> None:
        frame = ttk.Frame(self.page_formulas, padding=10)
        frame.pack(fill='both', expand=True)
        self.formulas_text = tk.Text(frame, wrap='word', font=('Courier New', 10))
        self.formulas_text.pack(fill='both', expand=True)
        self.formulas_text.insert('1.0', 'После расчёта здесь появится развёрнутый инженерный вывод формулами и буквами.')
        self.formulas_text.config(state='disabled')

    def _collect_inputs(self) -> Dict[str, Any]:
        data = {key: var.get() for key, var in self.vars.items()}
        data['shema_tf'] = int(data['shema_tf'])
        return data

    def run_calculation(self) -> None:
        try:
            inputs = self._collect_inputs()
            mode_data = {
                'mode_id': 'STATIC_V2',
                'Nz': inputs['Nz'],
                'Gprom': inputs['Gprom'],
                'Qtf': inputs['Qtf'],
                'shema_tf': inputs['shema_tf'],
                't_water_in': inputs['t_water_in'],
                'G_water_psg': inputs['G_water_psg'],
            }
            calc = run_mode_calculation(mode_data)
            self.results = calc['results']
            self.eco = calculate_economics_from_results(self.results, boiler_efficiency=0.92, fuel_price_rub_per_tut=inputs['fuel_price'])
            self.balance = calculate_station_steam_balance(self.results)
            self.limits = evaluate_limits(
                power_mw=float(self.results.get('N_el_actual', self.results.get('N_el_gross', 0.0))),
                steam_flow_tph=float(self.results.get('G0', 0.0)),
                condenser_kpa=float(self.results.get('P_k', 0.0)) * 1000.0,
                fresh_steam_temp_c=float(inputs['fresh_steam_temp']),
                tech_limit_mw=float(inputs['tech_limit_mw']),
            )
            self._update_summary(inputs)
            self._update_block_pages()
            self._update_formulas(inputs)
            self.notebook.select(self.page_summary)
        except Exception as exc:
            messagebox.showerror('Ошибка расчёта', str(exc))

    def _summary_rows(self) -> List[tuple]:
        if not self.results:
            return []
        rows = [
            ('Электрическая мощность брутто', self.results.get('N_el_gross'), 'МВт'),
            ('Электрическая мощность нетто', self.results.get('N_el_net'), 'МВт'),
            ('Расход свежего пара', self.results.get('G0'), 'т/ч'),
            ('Тепловая мощность Q0', self.results.get('Q0'), 'Гкал/ч'),
            ('КПД брутто', self.results.get('eta_brut'), '%'),
            ('КПД нетто', self.results.get('eta_net'), '%'),
            ('Удельный расход тепла брутто', self.results.get('q_t'), 'ккал/кВт·ч'),
            ('Давление в конденсаторе', float(self.results.get('P_k', 0.0)) * 1000.0, 'кПа'),
            ('Промышленный отбор', self.results.get('Gprom'), 'т/ч'),
            ('Верхний теплофикационный отбор', self.results.get('G_vto'), 'т/ч'),
            ('Нижний теплофикационный отбор', self.results.get('G_nto'), 'т/ч'),
            ('Пар в конденсатор', self.results.get('G_cond'), 'т/ч'),
            ('Невязка баланса', self.results.get('delta_balance'), 'т/ч'),
        ]
        if self.eco:
            rows.extend([
                ('Общий КПД с котлом', float(self.eco.get('eta_total', 0.0)) * 100.0, '%'),
                ('УРУТ', self.eco.get('urut_g_per_kwh'), 'г/кВт·ч'),
                ('Топливная стоимость', self.eco.get('fuel_cost_rub_per_mwh'), 'руб/МВт·ч'),
            ])
        return rows

    def _update_summary(self, inputs: Dict[str, Any]) -> None:
        for item in self.summary_tree.get_children():
            self.summary_tree.delete(item)
        for label, value, unit in self._summary_rows():
            shown = f"{float(value):.3f}" if isinstance(value, (int, float)) and abs(float(value)) < 10 else f"{float(value):.2f}" if isinstance(value, (int, float)) else str(value)
            self.summary_tree.insert('', 'end', text=label, values=(shown, unit))

        summary_lines = [
            'Сводный инженерный вывод',
            '',
            f"Режим: Nz={inputs['Nz']:.2f} МВт, Gпром={inputs['Gprom']:.2f} т/ч, Qтф={inputs['Qtf']:.2f} Гкал/ч.",
            f"Сходимость: {int(self.results.get('iterations', 0))} итераций; невязка {float(self.results.get('delta_balance', 0.0)):.3f} т/ч.",
            f"Итог: Nнетто={float(self.results.get('N_el_net', 0.0)):.2f} МВт, G0={float(self.results.get('G0', 0.0)):.2f} т/ч, Pк={float(self.results.get('P_k', 0.0))*1000.0:.2f} кПа.",
        ]
        if self.eco:
            summary_lines.append(
                f"Экономика: УРУТ={float(self.eco.get('urut_g_per_kwh', 0.0)):.2f} г/кВт·ч; топливо={float(self.eco.get('fuel_cost_rub_per_mwh', 0.0)):.2f} руб/МВт·ч."
            )
        if self.limits:
            if self.limits.get('has_limit'):
                summary_lines.append('Ограничения: ' + ', '.join(self.limits.get('violations', [])))
            else:
                summary_lines.append('Ограничения: активных нарушений по встроенным правилам не обнаружено.')
        if self.balance:
            summary_lines.append(
                f"Баланс пара: регенерация={float(self.balance.get('regeneration_extractions_tph', 0.0)):.2f} т/ч; "
                f"в конденсатор={float(self.balance.get('to_condenser_tph', 0.0)):.2f} т/ч."
            )

        self.summary_text.config(state='normal')
        self.summary_text.delete('1.0', 'end')
        self.summary_text.insert('1.0', '\n'.join(summary_lines))
        self.summary_text.config(state='disabled')

        self._draw_summary_chart()

    def _draw_summary_chart(self) -> None:
        for child in self.summary_chart_frame.winfo_children():
            child.destroy()
        if not self.results:
            return
        labels = ['Nбрутто', 'Nнетто', 'G0', 'Q0', 'Pк']
        values = [
            float(self.results.get('N_el_gross', 0.0)),
            float(self.results.get('N_el_net', 0.0)),
            float(self.results.get('G0', 0.0)),
            float(self.results.get('Q0', 0.0)),
            float(self.results.get('P_k', 0.0)) * 1000.0,
        ]
        fig = Figure(figsize=(9, 3.5), dpi=100)
        ax = fig.add_subplot(111)
        ax.bar(labels, values)
        ax.set_ylabel('Значение в собственных единицах')
        ax.set_title('Ключевые показатели режима')
        canvas = FigureCanvasTkAgg(fig, master=self.summary_chart_frame)
        canvas.draw()
        canvas.get_tk_widget().pack(fill='both', expand=True)

    def _psg_component_data(self) -> Dict[str, Any]:
        if not self.results:
            return {'name': 'ПСГ / ПСВ', 'data': []}
        data: List[tuple] = []
        if isinstance(self.results.get('psv1'), dict):
            p1 = self.results['psv1']
            data.extend([
                ('Расход сетевой воды', self.results.get('G_water_tph', 0.0), 'т/ч'),
                ('Температура воды на входе', p1.get('t_water_in_c', 0.0), '°C'),
                ('Температура воды на выходе', p1.get('t_water_out_c', 0.0), '°C'),
                ('Расход греющего пара', p1.get('G_steam_tph', 0.0), 'т/ч'),
                ('Давление греющего пара', p1.get('P_steam_mpa', 0.0), 'МПа'),
                ('Температура насыщения', p1.get('t_sat_c', 0.0), '°C'),
            ])
        else:
            nto = self.results.get('psv_nto', {}) if isinstance(self.results.get('psv_nto'), dict) else {}
            vto = self.results.get('psv_vto', {}) if isinstance(self.results.get('psv_vto'), dict) else {}
            data.extend([
                ('Расход сетевой воды', self.results.get('G_water_tph', 0.0), 'т/ч'),
                ('ПСГ-1/НТО: расход пара', nto.get('G_steam_tph', 0.0), 'т/ч'),
                ('ПСГ-1/НТО: давление', nto.get('P_steam_mpa', 0.0), 'МПа'),
                ('ПСГ-1/НТО: температура выхода воды', nto.get('t_water_out_c', 0.0), '°C'),
                ('ПСГ-2/ВТО: расход пара', vto.get('G_steam_tph', 0.0), 'т/ч'),
                ('ПСГ-2/ВТО: давление', vto.get('P_steam_mpa', 0.0), 'МПа'),
                ('ПСГ-2/ВТО: температура выхода воды', vto.get('t_water_out_c', 0.0), '°C'),
                ('Температура воды после ПСГ', self.results.get('t_water_final_c', 0.0), '°C'),
            ])
        return {'name': 'ПСГ / ПСВ', 'data': data}

    def _component_map(self) -> Dict[str, Dict[str, Any]]:
        components = dict(self.results.get('components', {})) if self.results else {}
        components['psg'] = self._psg_component_data()
        return components

    def _update_block_pages(self) -> None:
        if not self.results:
            return
        components = self._component_map()
        for key, page in self.block_pages.items():
            tree = page['tree']
            for item in tree.get_children():
                tree.delete(item)
            comp = components.get(key, {'name': key, 'data': []})
            for row in comp.get('data', []):
                label, value, unit = row
                if isinstance(value, (int, float)):
                    shown = f"{float(value):.3f}" if abs(float(value)) < 10 else f"{float(value):.2f}"
                else:
                    shown = str(value)
                tree.insert('', 'end', text=label, values=(shown, unit))
            self._draw_block_chart(key, comp.get('data', []))

    def _draw_block_chart(self, key: str, rows: List[tuple]) -> None:
        frame = self.block_pages[key]['chart_frame']
        for child in frame.winfo_children():
            child.destroy()
        numeric_rows = []
        for label, value, unit in rows:
            if isinstance(value, (int, float)) and math.isfinite(float(value)):
                numeric_rows.append((label, float(value), unit))
        if not numeric_rows:
            ttk.Label(frame, text='Для этого блока пока нет числовых данных для графика.').grid(row=0, column=0, sticky='nw')
            return
        labels = [item[0] for item in numeric_rows[:6]]
        values = [item[1] for item in numeric_rows[:6]]
        fig = Figure(figsize=(5.2, 3.2), dpi=100)
        ax = fig.add_subplot(111)
        ax.bar(range(len(values)), values)
        ax.set_xticks(range(len(values)))
        ax.set_xticklabels([label[:18] + ('…' if len(label) > 18 else '') for label in labels], rotation=35, ha='right')
        ax.set_title('Параметры блока')
        ax.grid(axis='y', alpha=0.25)
        fig.tight_layout()
        canvas = FigureCanvasTkAgg(fig, master=frame)
        canvas.draw()
        canvas.get_tk_widget().grid(row=0, column=0, sticky='nsew')

    def _update_formulas(self, inputs: Dict[str, Any]) -> None:
        report = build_human_formula_report(self.results or {}, inputs)
        self.formulas_text.config(state='normal')
        self.formulas_text.delete('1.0', 'end')
        self.formulas_text.insert('1.0', report)
        self.formulas_text.config(state='disabled')


def run_static_app() -> None:
    root = tk.Tk()
    app = StaticPT80App(root)
    root.mainloop()
