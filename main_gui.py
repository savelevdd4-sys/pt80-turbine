import io
import json
import math
import re
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox, Canvas, Scrollbar
import xml.etree.ElementTree as ET

import matplotlib
matplotlib.use('TkAgg')
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import numpy as np
try:
    from services.calc_service import run_mode_calculation
except ImportError:
    from calc_service import run_mode_calculation
try:
    from models.environment_models import air_to_water_temp, condenser_pressure_from_water_temp, environmental_power_correction
except ImportError:
    from environment_models import air_to_water_temp, condenser_pressure_from_water_temp, environmental_power_correction
try:
    from models.regeneration_view import build_regeneration_view
except ImportError:
    from regeneration_view import build_regeneration_view
try:
    from models.steam_balance import calculate_station_steam_balance
except ImportError:
    from steam_balance import calculate_station_steam_balance
try:
    from models.turbine_limits import evaluate_limits
except ImportError:
    from turbine_limits import evaluate_limits
try:
    from models.economics import calculate_economics_from_results
except ImportError:
    from economics import calculate_economics_from_results
try:
    from models.profit_optimizer import optimize_load_by_profit
except ImportError:
    from profit_optimizer import optimize_load_by_profit
try:
    from models.market import build_day_ahead_schedule
except ImportError:
    from market import build_day_ahead_schedule
from gui_charts import *
from steam_properties import ts, h_steam, h_water_temp, h_steam_sat, h_water

try:
    import cairosvg
except Exception:
    cairosvg = None

try:
    from PIL import Image, ImageTk, ImageDraw
except Exception:
    Image = None
    ImageTk = None
from config import P0, t0, Fk, W_nom, tw1_nom, Pd, ts_d, beta_vozvrat, etam, etag_nom
try:
    from models.psg import calc_psg
except ImportError:
    from psg import calc_psg
dynamic_import_error = None
run_dynamic_simulation = None
list_dynamic_scenarios = None
build_dynamic_table_for_ui = None

try:
    from services.dynamic_service import run_dynamic_simulation, list_dynamic_scenarios, build_dynamic_table_for_ui
except Exception as e_services:
    try:
        from dynamic_service import run_dynamic_simulation, list_dynamic_scenarios, build_dynamic_table_for_ui
    except Exception as e_root:
        dynamic_import_error = f"services.dynamic_service: {e_services}; dynamic_service: {e_root}"
        try:
            from dynamic_scenarios import list_scenarios as _list_scenarios_fallback, SCENARIO_LABELS as _SCENARIO_LABELS_FALLBACK

            def list_dynamic_scenarios():
                return [
                    {"key": key, "label": _SCENARIO_LABELS_FALLBACK.get(key, key)}
                    for key in _list_scenarios_fallback()
                ]
        except Exception as e_scen:
            dynamic_import_error = f"{dynamic_import_error}; dynamic_scenarios: {e_scen}"
class PT80App:
    def __init__(self, root):
        self.root = root
        self.root.title("ПТ-80 ТЭЦ — Диспетчерский расчёт")
        self.root.geometry("1320x820")
        self.root.configure(bg='gray')
        self.results = None
        self.optimum = None
        self.schedule = None
        self.limits = None
        self.eco = None
        self.regen_rows = None
        self.balance = None
        self.dynamic_result = None
        self.dynamic_table_df = None
        self.dynamic_summary = None
        self.dynamic_scenarios = list_dynamic_scenarios() if callable(list_dynamic_scenarios) else []
        self.dynamic_scenario_map = {item['label']: item['key'] for item in self.dynamic_scenarios}
        self.dynamic_scenario_labels = [item['label'] for item in self.dynamic_scenarios]
        self.dynamic_scenario_var = tk.StringVar(value=self.dynamic_scenario_labels[0] if self.dynamic_scenario_labels else '')
        self.dynamic_t_end_var = tk.DoubleVar(value=600.0)
        self.dynamic_n_points_var = tk.IntVar(value=1201)
        self.dynamic_plot_choice = tk.StringVar(value='Мощность')
        # Данные для дополнительных графиков
        self.power_steam_data = None
        self.heat_power_data = None
        self.temp_pressure_data = None
        self.csnd_pressures = None
        self.hs_points = None
        self.last_params = None
        self.environment_context = None
        self.health_vars = {}
        self.health_state_labels = {}
        self.scheme_items = {}
        self.scheme_text_items = {}
        self.scheme_background_item = None
        self.scheme_background_photo = None
        self.scheme_background_size = (1191, 842)
        self.scheme_source_size = (1191.0, 842.0)
        self.scheme_render_cache = {}
        self.scheme_svg_path = self._resolve_scheme_svg_path()
        self.scheme_png_path = self._resolve_scheme_png_path()
        self.component_svg_map = {
       'cvd': ['cvd'],
      'csnd': ['cnd'],   # было: ['csd', 'cnd']
      'generator': ['generator'],
     'pvd7': ['p7'],
      'pvd6': ['p6'],
     'pvd5': ['p5'],
     'pnd4': ['pnd4'],
     'pnd3': ['pnd3'],
     'pnd2': ['pnd2'],
     'pnd1': ['pnd5'],
     'deaerator': ['deaerator'],
     'condenser': ['condenser'],
     'psg1': ['psg1'],
     'psg2': ['astg2'],
     }
        self.svg_object_bounds = self._load_svg_object_bounds()
        self.default_component_layout = {
            'cvd': {'title': 'ЦВД', 'coords': (272.0, 51.0, 412.0, 121.0)},
            'csnd': {'title': 'ЦСНД', 'coords': (558.0, 42.0, 718.0, 112.0)},
            'generator': {'title': 'G', 'coords': (910.0, 41.0, 1030.0, 111.0)},
            'pvd7': {'title': 'ПВД-7', 'coords': (436.0, 87.0, 546.0, 137.0)},
            'pvd6': {'title': 'ПВД-6', 'coords': (442.0, 148.0, 552.0, 198.0)},
            'pvd5': {'title': 'ПВД-5', 'coords': (443.0, 209.0, 553.0, 259.0)},
            'pnd1': {'title': 'ПНД-1', 'coords': (741.0, 80.0, 851.0, 130.0)},
            'pnd2': {'title': 'ПНД-2', 'coords': (745.0, 140.0, 855.0, 190.0)},
            'pnd3': {'title': 'ПНД-3', 'coords': (747.0, 197.0, 857.0, 247.0)},
            'pnd4': {'title': 'ПНД-4', 'coords': (747.0, 253.0, 857.0, 303.0)},
            'deaerator': {'title': 'Деаэратор', 'coords': (569.0, 171.0, 719.0, 246.0)},
            'condenser': {'title': 'Конденсатор', 'coords': (878.0, 118.0, 1078.0, 198.0)},
            'psg1': {'title': 'ПСГ-1', 'coords': (876.0, 211.0, 986.0, 261.0)},
            'psg2': {'title': 'ПСГ-2', 'coords': (998.0, 210.0, 1108.0, 260.0)},
        }
        self.component_layout = self.load_component_layout()
        self.scheme_connections = [
            ('cvd', 'csnd'),
            ('csnd', 'generator'),
            ('cvd', 'pvd7'),
            ('cvd', 'pvd6'),
            ('cvd', 'pvd5'),
            ('pvd7', 'pvd6'),
            ('pvd6', 'pvd5'),
            ('csnd', 'pnd1'),
            ('csnd', 'pnd2'),
            ('csnd', 'pnd3'),
            ('csnd', 'pnd4'),
            ('pnd1', 'pnd2'),
            ('pnd2', 'pnd3'),
            ('pnd3', 'pnd4'),
            ('pnd4', 'deaerator'),
            ('deaerator', 'pvd5'),
            ('csnd', 'condenser'),
            ('csnd', 'psg1'),
            ('csnd', 'psg2'),
            ('psg1', 'psg2'),
            ('condenser', 'psg1'),
            ('condenser', 'psg2'),
        ]
        self.create_widgets()
    def create_widgets(self):
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill='both', expand=True, padx=5, pady=5)
        # Страница 1: Исходные данные + схема
        self.input_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.input_tab, text="Исходные данные")
        self.create_input_tab()
        # Страница 2: Расчёт (краткие результаты)
        self.results_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.results_tab, text="Расчёт")
        self.create_results_tab()
        # Страница 3: Компоненты (детальные параметры)
        self.components_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.components_tab, text="Компоненты")
        self.create_components_tab()
        # Страница 4: Формулы
        self.formulas_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.formulas_tab, text="Формулы")
        self.create_formulas_tab()
    def create_input_tab(self):
        frame = ttk.Frame(self.input_tab, padding=8)
        frame.pack(fill='both', expand=True)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=2)
        frame.rowconfigure(1, weight=3)

        top_frame = ttk.Frame(frame)
        top_frame.grid(row=0, column=0, sticky='nsew', pady=(0, 8))
        top_frame.columnconfigure(0, weight=3)
        top_frame.columnconfigure(1, weight=2)
        top_frame.rowconfigure(0, weight=1)

        left_frame = ttk.LabelFrame(top_frame, text="Входные данные", padding=10)
        left_frame.grid(row=0, column=0, sticky='nsew', padx=(0, 8))
        left_frame.columnconfigure(0, weight=1)
        left_frame.columnconfigure(1, weight=0)
        fields = [
            ("Целевая электрическая мощность, МВт", "Nz", 80.0),
            ("Производственный отбор, т/ч", "Gprom", 0.0),
            ("Тепловая нагрузка, Гкал/ч", "Qtf", 60.0),
            ("Схема теплофикации (1 - одноступ., 2 - двухступ.)", "shema_tf", 1),
            ("Температура воздуха, °C", "t_air", 15.0),
            ("Цена топлива, руб/т у.т.", "fuel_price", 6000.0),
            ("Ожидаемая цена РСВ, руб/МВт·ч", "market_price", 2500.0),
            ("Техническое ограничение по мощности, МВт", "tech_limit_mw", 100.0),
            ("Температура свежего пара, °C", "fresh_steam_temp", 555.0),
        ]
        self.input_vars = {}
        for row, (label_text, key, default) in enumerate(fields):
            ttk.Label(left_frame, text=label_text, anchor='w').grid(row=row, column=0, sticky='w', pady=2, padx=(0, 8))
            var = tk.DoubleVar(value=default)
            ttk.Entry(left_frame, textvariable=var, width=14).grid(row=row, column=1, sticky='ew', pady=2)
            self.input_vars[key] = var
        button_row = len(fields)
        ttk.Button(left_frame, text="Рассчитать", command=self.run_calculation).grid(
            row=button_row, column=0, columnspan=2, pady=(12, 0), sticky='ew'
        )

        right_frame = ttk.LabelFrame(top_frame, text="Пропускная способность оборудования, %", padding=10)
        right_frame.grid(row=0, column=1, sticky='nsew')
        right_frame.columnconfigure(0, weight=1)
        right_frame.columnconfigure(1, weight=0)
        right_frame.columnconfigure(2, weight=1)
        components = [
            ('cvd', 'ЦВД'),
            ('csnd', 'ЦСНД'),
            ('condenser', 'Конденсатор'),
            ('pvd7', 'ПВД-7'),
            ('pvd6', 'ПВД-6'),
            ('pvd5', 'ПВД-5'),
            ('pnd4', 'ПНД-4'),
            ('pnd3', 'ПНД-3'),
            ('pnd2', 'ПНД-2'),
            ('pnd1', 'ПНД-1'),
            ('deaerator', 'Деаэратор'),
            ('psg1', 'ПСГ-1'),
            ('psg2', 'ПСГ-2'),
            ('generator', 'Генератор'),
        ]
        self.health_vars = {}
        self.health_state_labels = {}
        for row, (key, title) in enumerate(components):
            ttk.Label(right_frame, text=title, anchor='w').grid(row=row, column=0, sticky='w', pady=2, padx=(0, 6))
            var = tk.StringVar(value='100.0')
            spin = tk.Spinbox(
                right_frame,
                from_=0.0,
                to=100.0,
                increment=0.5,
                textvariable=var,
                width=6,
                justify='right',
                command=self.on_health_change,
            )
            spin.grid(row=row, column=1, sticky='ew', pady=2, padx=(0, 6))
            spin.bind('<KeyRelease>', lambda _e, _k=key: self.on_health_change(_k))
            spin.bind('<FocusOut>', lambda _e, _k=key: self.on_health_change(_k))
            self.health_vars[key] = var
            state_label = ttk.Label(right_frame, text='Исправное', foreground='#1b8a3b')
            state_label.grid(row=row, column=2, sticky='w', pady=2)
            self.health_state_labels[key] = state_label

        scheme_frame = ttk.LabelFrame(frame, text="Схема оборудования (SVG)", padding=6)
        scheme_frame.grid(row=1, column=0, sticky='nsew')
        scheme_frame.rowconfigure(0, weight=1)
        scheme_frame.columnconfigure(0, weight=1)
        self.scheme_canvas = tk.Canvas(scheme_frame, bg='white', highlightthickness=0)
        self.scheme_canvas.grid(row=0, column=0, sticky='nsew')
        x_scroll = ttk.Scrollbar(scheme_frame, orient='horizontal', command=self.scheme_canvas.xview)
        y_scroll = ttk.Scrollbar(scheme_frame, orient='vertical', command=self.scheme_canvas.yview)
        self.scheme_canvas.configure(xscrollcommand=x_scroll.set, yscrollcommand=y_scroll.set)
        x_scroll.grid(row=1, column=0, sticky='ew')
        y_scroll.grid(row=0, column=1, sticky='ns')
        self.scheme_canvas.bind('<Configure>', self._redraw_scheme)
        self.refresh_health_panel()
        self._redraw_scheme()
    def _resolve_scheme_svg_path(self):
        candidates = [
            Path(__file__).resolve().with_name('pt80_exact_with_areas.svg'),
            Path.cwd() / 'pt80_exact_with_areas.svg',
            Path('pt80_exact_with_areas.svg'),
        ]
        for candidate in candidates:
            if candidate.exists():
                return candidate
        return candidates[0]

    def _resolve_scheme_png_path(self):
        candidates = [
            Path(__file__).resolve().with_name('pt80_exact_with_areas.png'),
            Path.cwd() / 'pt80_exact_with_areas.png',
            Path('pt80_exact_with_areas.png'),
        ]
        for candidate in candidates:
            if candidate.exists():
                return candidate
        return candidates[0]

    def _load_svg_tree(self):
        cached = getattr(self, '_svg_tree_cache', None)
        if cached is not None:
            return cached
        if not self.scheme_svg_path.exists():
            self._svg_tree_cache = (None, {})
            return self._svg_tree_cache
        try:
            root = ET.parse(self.scheme_svg_path).getroot()
        except Exception:
            self._svg_tree_cache = (None, {})
            return self._svg_tree_cache
        refs = {}
        for element in root.iter():
            element_id = element.attrib.get('id')
            if element_id:
                refs[element_id] = element
        view_box = root.attrib.get('viewBox', '').replace(',', ' ').split()
        if len(view_box) == 4:
            try:
                self.scheme_source_size = (float(view_box[2]), float(view_box[3]))
            except Exception:
                pass
        self._svg_tree_cache = (root, refs)
        return self._svg_tree_cache

    def _parse_style_string(self, value):
        result = {}
        if not value:
            return result
        for chunk in str(value).split(';'):
            if ':' not in chunk:
                continue
            key, raw = chunk.split(':', 1)
            result[key.strip()] = raw.strip()
        return result

    def _parse_svg_color(self, value):
        if value is None:
            return ''
        value = str(value).strip()
        if not value or value.lower() == 'none':
            return ''
        if value.startswith('#'):
            if len(value) == 4:
                return '#' + ''.join(ch * 2 for ch in value[1:])
            return value
        match = re.fullmatch(r'rgb\(\s*([0-9.]+)(%)?\s*,\s*([0-9.]+)(%)?\s*,\s*([0-9.]+)(%)?\s*\)', value)
        if match:
            parts = []
            for index in (1, 3, 5):
                number = float(match.group(index))
                is_percent = bool(match.group(index + 1))
                channel = round(255 * number / 100.0) if is_percent else round(number)
                parts.append(max(0, min(255, int(channel))))
            return '#%02x%02x%02x' % tuple(parts)
        named = {
            'black': '#000000',
            'white': '#ffffff',
            'red': '#ff0000',
            'green': '#008000',
            'blue': '#0000ff',
            'gray': '#808080',
            'grey': '#808080',
            'yellow': '#ffff00',
            'orange': '#ffa500',
        }
        return named.get(value.lower(), value)

    def _safe_float(self, value, default=0.0):
        try:
            return float(value)
        except Exception:
            return float(default)

    def _matrix_scale(self, matrix):
        a, b, c, d, _e, _f = matrix
        sx = math.hypot(a, b)
        sy = math.hypot(c, d)
        scale = (sx + sy) / 2.0
        return scale if scale > 0 else 1.0

    def _merge_svg_paint(self, element, inherited=None, render_state=None, from_use=False):
        paint = dict(inherited or {})
        defaults = {
         'fill': '',
         'stroke': '',
         'stroke-width': '1',
         'fill-opacity': '1',
         'stroke-opacity': '1',
         'stroke-linecap': 'butt',
          'stroke-linejoin': 'miter',
         }
        for key, value in defaults.items():
            paint.setdefault(key, value)
        style_map = self._parse_style_string(element.attrib.get('style', ''))
        for key in defaults:
            if key in element.attrib:
                paint[key] = element.attrib.get(key, paint.get(key))
            if key in style_map:
                paint[key] = style_map[key]

        classes = set(element.attrib.get('class', '').split())
        svg_key = element.attrib.get('data-object')
        if render_state and svg_key in render_state:
            if 'area-hit' in classes:
                paint['fill'] = render_state[svg_key]['fill']
                paint['fill-opacity'] = '0.22'
                paint['stroke'] = ''
                paint['_stipple'] = 'gray25'
            elif 'area-outline' in classes:
                paint['fill'] = ''
                paint['stroke'] = render_state[svg_key]['stroke']
                paint['stroke-width'] = '3'
                paint['stroke-opacity'] = '1'

        fill = self._parse_svg_color(paint.get('fill'))
        stroke = self._parse_svg_color(paint.get('stroke'))
        if from_use and fill and not stroke:
            stroke = fill
            fill = ''
            paint['stroke-width'] = paint.get('stroke-width', '1') or '1'
        paint['fill'] = fill
        paint['stroke'] = stroke
        return paint

    def _tk_capstyle(self, value):
        value = str(value or 'butt').lower()
        mapping = {
            'round': tk.ROUND,
            'square': tk.PROJECTING,
            'butt': tk.BUTT,
        }
        return mapping.get(value, tk.ROUND)

    def _tk_joinstyle(self, value):
        value = str(value or 'miter').lower()
        mapping = {
            'round': tk.ROUND,
            'bevel': tk.BEVEL,
            'miter': tk.MITER,
        }
        return mapping.get(value, tk.ROUND)

    def _flatten_points(self, points):
        flat = []
        for x, y in points:
            flat.extend((x, y))
        return flat

    def _sample_cubic(self, p0, p1, p2, p3, segments=14):
        points = []
        segments = max(2, int(segments))
        for step in range(1, segments + 1):
            t = step / float(segments)
            mt = 1.0 - t
            x = (mt ** 3) * p0[0] + 3 * (mt ** 2) * t * p1[0] + 3 * mt * (t ** 2) * p2[0] + (t ** 3) * p3[0]
            y = (mt ** 3) * p0[1] + 3 * (mt ** 2) * t * p1[1] + 3 * mt * (t ** 2) * p2[1] + (t ** 3) * p3[1]
            points.append((x, y))
        return points

    def _path_to_subpaths(self, d_value, matrix):
        tokens = re.findall(r'[MLCZ]|-?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?', d_value or '')
        index = 0
        current = []
        subpaths = []
        cursor = None
        start = None
        command = None
        while index < len(tokens):
            token = tokens[index]
            if re.fullmatch(r'[MLCZ]', token):
                command = token
                index += 1
            if command == 'M':
                if index + 1 >= len(tokens):
                    break
                x = float(tokens[index])
                y = float(tokens[index + 1])
                index += 2
                if current:
                    subpaths.append({'points': current, 'closed': False})
                pt = self._apply_affine(matrix, x, y)
                current = [pt]
                cursor = (x, y)
                start = (x, y)
                command = 'L'
            elif command == 'L':
                if index + 1 >= len(tokens) or cursor is None:
                    break
                x = float(tokens[index])
                y = float(tokens[index + 1])
                index += 2
                current.append(self._apply_affine(matrix, x, y))
                cursor = (x, y)
            elif command == 'C':
                if index + 5 >= len(tokens) or cursor is None:
                    break
                x1 = float(tokens[index]); y1 = float(tokens[index + 1])
                x2 = float(tokens[index + 2]); y2 = float(tokens[index + 3])
                x3 = float(tokens[index + 4]); y3 = float(tokens[index + 5])
                index += 6
                sampled = self._sample_cubic(cursor, (x1, y1), (x2, y2), (x3, y3))
                current.extend(self._apply_affine(matrix, x, y) for x, y in sampled)
                cursor = (x3, y3)
            elif command == 'Z':
                if current:
                    if start is not None:
                        start_pt = self._apply_affine(matrix, start[0], start[1])
                        if current[-1] != start_pt:
                            current.append(start_pt)
                    subpaths.append({'points': current, 'closed': True})
                current = []
                cursor = start
                command = None
            else:
                index += 1
        if current:
            subpaths.append({'points': current, 'closed': False})
        return subpaths

    def _draw_subpaths(self, canvas, subpaths, paint, matrix):
        scale = self._matrix_scale(matrix)
        fill = paint.get('fill', '')
        stroke = paint.get('stroke', '')
        fill_opacity = self._safe_float(paint.get('fill-opacity', 1.0), 1.0)
        stroke_opacity = self._safe_float(paint.get('stroke-opacity', 1.0), 1.0)
        line_width = max(1.0, self._safe_float(paint.get('stroke-width', 1.0), 1.0) * scale)
        capstyle = self._tk_capstyle(paint.get('stroke-linecap'))
        joinstyle = self._tk_joinstyle(paint.get('stroke-linejoin'))
        stipple = paint.get('_stipple', '') if fill and fill_opacity < 1.0 else ''

        if fill and fill_opacity > 0:
            for subpath in subpaths:
                points = subpath.get('points', [])
                if len(points) >= 3:
                    canvas.create_polygon(
                        self._flatten_points(points),
                        fill=fill,
                        outline='',
                        stipple=stipple,
                    )

        if stroke and stroke_opacity > 0:
            for subpath in subpaths:
                points = subpath.get('points', [])
                if len(points) >= 2:
                    canvas.create_line(
                        self._flatten_points(points),
                        fill=stroke,
                        width=line_width,
                        capstyle=capstyle,
                        joinstyle=joinstyle,
                        smooth=False,
                    )

    def _rect_subpaths(self, element, matrix):
        x = self._safe_float(element.attrib.get('x', 0.0))
        y = self._safe_float(element.attrib.get('y', 0.0))
        width = self._safe_float(element.attrib.get('width', 0.0))
        height = self._safe_float(element.attrib.get('height', 0.0))
        points = [
            self._apply_affine(matrix, x, y),
            self._apply_affine(matrix, x + width, y),
            self._apply_affine(matrix, x + width, y + height),
            self._apply_affine(matrix, x, y + height),
            self._apply_affine(matrix, x, y),
        ]
        return [{'points': points, 'closed': True}]

    def _polygon_subpaths(self, element, matrix):
        raw_points = element.attrib.get('points', '').replace(',', ' ').split()
        nums = [self._safe_float(value) for value in raw_points if value]
        pairs = list(zip(nums[0::2], nums[1::2]))
        points = [self._apply_affine(matrix, x, y) for x, y in pairs]
        if points and points[0] != points[-1]:
            points.append(points[0])
        return [{'points': points, 'closed': True}] if points else []

    def _ellipse_subpaths(self, element, matrix):
        cx = self._safe_float(element.attrib.get('cx', 0.0))
        cy = self._safe_float(element.attrib.get('cy', 0.0))
        rx = self._safe_float(element.attrib.get('rx', 0.0))
        ry = self._safe_float(element.attrib.get('ry', 0.0))
        points = []
        for step in range(49):
            angle = 2.0 * math.pi * step / 48.0
            x = cx + rx * math.cos(angle)
            y = cy + ry * math.sin(angle)
            points.append(self._apply_affine(matrix, x, y))
        return [{'points': points, 'closed': True}]

    def _draw_svg_node(self, canvas, element, matrix, refs, render_state, inherited_paint=None, from_use=False):
        tag = self._svg_tag(element.tag)
        if tag in {'defs', 'namedview', 'style', 'script'}:
            return
        local_matrix = self._mul_affine(matrix, self._parse_transform(element.attrib.get('transform', '')))
        current_paint = self._merge_svg_paint(element, inherited=inherited_paint, render_state=render_state, from_use=from_use)

        if tag in {'svg', 'g'}:
            for child in list(element):
                self._draw_svg_node(canvas, child, local_matrix, refs, render_state, inherited_paint=current_paint, from_use=from_use)
            return

        if tag == 'use':
            href = element.attrib.get('{http://www.w3.org/1999/xlink}href') or element.attrib.get('href', '')
            ref_id = href[1:] if href.startswith('#') else href
            ref_element = refs.get(ref_id)
            if ref_element is None:
                return
            x = self._safe_float(element.attrib.get('x', 0.0))
            y = self._safe_float(element.attrib.get('y', 0.0))
            use_matrix = self._mul_affine(local_matrix, (1.0, 0.0, 0.0, 1.0, x, y))
            self._draw_svg_node(canvas, ref_element, use_matrix, refs, render_state, inherited_paint=current_paint, from_use=True)
            return

        subpaths = []
        if tag == 'path':
            subpaths = self._path_to_subpaths(element.attrib.get('d', ''), local_matrix)
        elif tag == 'rect':
            subpaths = self._rect_subpaths(element, local_matrix)
        elif tag == 'polygon':
            subpaths = self._polygon_subpaths(element, local_matrix)
        elif tag == 'ellipse':
            subpaths = self._ellipse_subpaths(element, local_matrix)

        if subpaths:
            self._draw_subpaths(canvas, subpaths, current_paint, local_matrix)

    def _svg_tag(self, tag):
        return tag.rsplit('}', 1)[-1] if '}' in tag else tag

    def _parse_transform(self, value):
        matrix = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
        if not value:
            return matrix
        transform = value.strip()
        while transform:
            if transform.startswith('matrix('):
                raw, transform = transform[7:].split(')', 1)
                vals = [float(v) for v in raw.replace(',', ' ').split() if v]
                if len(vals) == 6:
                    matrix = self._mul_affine(matrix, tuple(vals))
            elif transform.startswith('translate('):
                raw, transform = transform[10:].split(')', 1)
                vals = [float(v) for v in raw.replace(',', ' ').split() if v]
                tx = vals[0] if vals else 0.0
                ty = vals[1] if len(vals) > 1 else 0.0
                matrix = self._mul_affine(matrix, (1.0, 0.0, 0.0, 1.0, tx, ty))
            elif transform.startswith('scale('):
                raw, transform = transform[6:].split(')', 1)
                vals = [float(v) for v in raw.replace(',', ' ').split() if v]
                sx = vals[0] if vals else 1.0
                sy = vals[1] if len(vals) > 1 else sx
                matrix = self._mul_affine(matrix, (sx, 0.0, 0.0, sy, 0.0, 0.0))
            else:
                break
            transform = transform.lstrip()
        return matrix

    def _mul_affine(self, left, right):
        a1, b1, c1, d1, e1, f1 = left
        a2, b2, c2, d2, e2, f2 = right
        return (
            a1 * a2 + c1 * b2,
            b1 * a2 + d1 * b2,
            a1 * c2 + c1 * d2,
            b1 * c2 + d1 * d2,
            a1 * e2 + c1 * f2 + e1,
            b1 * e2 + d1 * f2 + f1,
        )

    def _apply_affine(self, matrix, x, y):
        a, b, c, d, e, f = matrix
        return a * x + c * y + e, b * x + d * y + f

    def _bbox_from_points(self, points):
        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        return (min(xs), min(ys), max(xs), max(ys))

    def _union_bbox(self, first, second):
        if first is None:
            return second
        if second is None:
            return first
        return (
            min(first[0], second[0]),
            min(first[1], second[1]),
            max(first[2], second[2]),
            max(first[3], second[3]),
        )

    def _element_bbox(self, element, matrix):
        tag = self._svg_tag(element.tag)
        try:
            if tag == 'rect':
                x = float(element.attrib.get('x', 0.0))
                y = float(element.attrib.get('y', 0.0))
                w = float(element.attrib.get('width', 0.0))
                h = float(element.attrib.get('height', 0.0))
                points = [
                    self._apply_affine(matrix, x, y),
                    self._apply_affine(matrix, x + w, y),
                    self._apply_affine(matrix, x + w, y + h),
                    self._apply_affine(matrix, x, y + h),
                ]
                return self._bbox_from_points(points)
            if tag == 'ellipse':
                cx = float(element.attrib.get('cx', 0.0))
                cy = float(element.attrib.get('cy', 0.0))
                rx = float(element.attrib.get('rx', 0.0))
                ry = float(element.attrib.get('ry', 0.0))
                points = [
                    self._apply_affine(matrix, cx - rx, cy - ry),
                    self._apply_affine(matrix, cx + rx, cy - ry),
                    self._apply_affine(matrix, cx + rx, cy + ry),
                    self._apply_affine(matrix, cx - rx, cy + ry),
                ]
                return self._bbox_from_points(points)
            if tag == 'polygon':
                raw_points = element.attrib.get('points', '').replace(',', ' ').split()
                nums = [float(v) for v in raw_points if v]
                pairs = list(zip(nums[0::2], nums[1::2]))
                if pairs:
                    points = [self._apply_affine(matrix, x, y) for x, y in pairs]
                    return self._bbox_from_points(points)
        except Exception:
            return None
        return None

    def _load_svg_object_bounds(self):
        if not self.scheme_svg_path.exists():
            return {}
        try:
            root = ET.parse(self.scheme_svg_path).getroot()
        except Exception:
            return {}
        bounds = {}

        def visit(node, inherited_matrix=(1.0, 0.0, 0.0, 1.0, 0.0, 0.0)):
            matrix = self._mul_affine(inherited_matrix, self._parse_transform(node.attrib.get('transform', '')))
            classes = node.attrib.get('class', '').split()
            data_object = node.attrib.get('data-object')
            if data_object and 'area-hit' in classes:
                bbox = self._element_bbox(node, matrix)
                if bbox is not None:
                    bounds[data_object] = self._union_bbox(bounds.get(data_object), bbox)
            for child in list(node):
                visit(child, matrix)

        visit(root)
        return bounds

    def _component_bbox_from_svg(self, component_key):
        bbox = None
        for svg_key in self.component_svg_map.get(component_key, []):
            bbox = self._union_bbox(bbox, self.svg_object_bounds.get(svg_key))
        return bbox

    def load_component_layout(self):
        layout = {key: dict(value) for key, value in self.default_component_layout.items()}
        for key in layout:
            svg_bbox = self._component_bbox_from_svg(key)
            if svg_bbox is not None:
                layout[key]['coords'] = tuple(float(v) for v in svg_bbox)
        layout_path = Path('scheme_layout.json')
        if layout_path.exists():
            try:
                data = json.loads(layout_path.read_text(encoding='utf-8'))
                for key, coords in data.items():
                    if key in layout and isinstance(coords, list) and len(coords) == 4:
                        layout[key]['coords'] = tuple(float(v) for v in coords)
            except Exception:
                pass
        return layout

    def normalize_percent(self, value):
        try:
            return max(0.0, min(100.0, float(value)))
        except Exception:
            return 100.0
    def get_integrity_style(self, percent):
        percent = self.normalize_percent(percent)
        if percent >= 98.0:
            return '#1b8a3b', 'Исправное'
        if percent >= 96.0:
            return '#f39c12', 'Незначительная поломка'
        if percent >= 94.0:
            return '#d35400', 'Значительная поломка'
        return '#c0392b', 'Предельное состояние'
    def get_temperature_outline(self, temperature):
        try:
            t = float(temperature)
        except Exception:
            return '#6c757d'
        if t < 30:
            return '#2e86de'
        if t < 60:
            return '#17a2b8'
        if t < 90:
            return '#28a745'
        if t < 130:
            return '#f1c40f'
        if t < 180:
            return '#e67e22'
        return '#c0392b'
    def _get_health_var_text(self, var):
        try:
            value = var.get()
        except tk.TclError:
            return ''
        return '' if value is None else str(value).strip()

    def on_health_change(self, component_key=None):
        self.refresh_health_panel()
        self._update_scheme_colors()

    def refresh_health_panel(self):
        for key, var in self.health_vars.items():
            raw_value = self._get_health_var_text(var)
            label = self.health_state_labels.get(key)
            if raw_value == '':
                if label is not None:
                    label.configure(text='Введите число', foreground='#6c757d')
                continue
            percent = self.normalize_percent(raw_value)
            var.set(f'{percent:.1f}')
            fill_color, state = self.get_integrity_style(percent)
            if label is not None:
                label.configure(text=state, foreground=fill_color)

    def collect_component_health(self):
        result = {}
        for key, var in self.health_vars.items():
            raw_value = self._get_health_var_text(var)
            result[key] = 100.0 if raw_value == '' else self.normalize_percent(raw_value)
        return result
    def _center(self, key):
        x1, y1, x2, y2 = self.component_layout[key]['coords']
        return (x1 + x2) / 2, (y1 + y2) / 2

    def _build_scheme_state(self):
        health = self.collect_component_health() if self.health_vars else {}
        temperatures = self.collect_component_temperatures()
        state = {}
        for component_key, svg_keys in self.component_svg_map.items():
            percent = health.get(component_key, 100.0)
            fill_color, _state = self.get_integrity_style(percent)
            stroke_color = self.get_temperature_outline(temperatures.get(component_key))
            for svg_key in svg_keys:
                state[svg_key] = {
                    'fill': fill_color,
                    'stroke': stroke_color,
                    'percent': percent,
                }
        return state

    def _hex_to_rgba(self, color, alpha):
        color = str(color).strip()
        if color.startswith('#') and len(color) == 7:
            try:
                r = int(color[1:3], 16)
                g = int(color[3:5], 16)
                b = int(color[5:7], 16)
                return (r, g, b, int(alpha))
            except Exception:
                pass
        return (108, 117, 125, int(alpha))

    def _overlay_component_state_on_image(self, image):
        if image is None or ImageDraw is None:
            return image
        try:
            rgba = image.convert('RGBA')
            overlay = Image.new('RGBA', rgba.size, (255, 255, 255, 0))
            draw = ImageDraw.Draw(overlay)
            health = self.collect_component_health() if self.health_vars else {}
            temperatures = self.collect_component_temperatures()
            base_w = max(float(self.scheme_source_size[0]), 1.0)
            base_h = max(float(self.scheme_source_size[1]), 1.0)
            sx = rgba.size[0] / base_w
            sy = rgba.size[1] / base_h
            line_w = max(2, int(round(3 * min(sx, sy))))
            radius = max(4, int(round(8 * min(sx, sy))))
            for key, meta in self.component_layout.items():
                coords = meta.get('coords')
                if not coords or len(coords) != 4:
                    continue
                x1, y1, x2, y2 = coords
                box = [x1 * sx, y1 * sy, x2 * sx, y2 * sy]
                percent = health.get(key, 100.0)
                fill_color, _state = self.get_integrity_style(percent)
                outline_color = self.get_temperature_outline(temperatures.get(key))
                fill_rgba = self._hex_to_rgba(fill_color, 58)
                outline_rgba = self._hex_to_rgba(outline_color, 215)
                if hasattr(draw, 'rounded_rectangle'):
                    draw.rounded_rectangle(box, radius=radius, fill=fill_rgba, outline=outline_rgba, width=line_w)
                else:
                    draw.rectangle(box, fill=fill_rgba, outline=outline_rgba, width=line_w)
            return Image.alpha_composite(rgba, overlay)
        except Exception:
            return image

    def _render_scheme_png(self, target_width):
        target_width = max(int(target_width), 400)

        # 1) Основной путь: живой рендер SVG через CairoSVG.
        if self.scheme_svg_path.exists() and cairosvg is not None and Image is not None and ImageTk is not None:
            render_state = self._build_scheme_state()
            cache_key = (
                'svg',
                int(target_width),
                tuple(sorted((key, value['fill'], value['stroke'], round(value['percent'], 3)) for key, value in render_state.items())),
            )
            cached = self.scheme_render_cache.get(cache_key)
            if cached is not None:
                return cached
            try:
                root = ET.parse(self.scheme_svg_path).getroot()
                for element in root.iter():
                    classes = element.attrib.get('class', '').split()
                    svg_key = element.attrib.get('data-object')
                    if svg_key not in render_state:
                        continue
                    style = None
                    if 'area-hit' in classes:
                        style = f"fill:{render_state[svg_key]['fill']};fill-opacity:0.18;stroke:none;pointer-events:all;"
                    elif 'area-outline' in classes:
                        style = f"fill:none;stroke:{render_state[svg_key]['stroke']};stroke-opacity:0.95;stroke-width:3;pointer-events:none;"
                    if style:
                        element.attrib['style'] = style
                png_bytes = cairosvg.svg2png(
                    bytestring=ET.tostring(root, encoding='utf-8'),
                    output_width=target_width,
                    background_color='white',
                )
                image = Image.open(io.BytesIO(png_bytes))
                image = self._overlay_component_state_on_image(image)
                photo = ImageTk.PhotoImage(image)
                result = (photo, image.size)
                if len(self.scheme_render_cache) > 6:
                    self.scheme_render_cache.clear()
                self.scheme_render_cache[cache_key] = result
                return result
            except Exception:
                pass

        # 2) Резервный путь: заранее подготовленный PNG.
        if self.scheme_png_path.exists() and Image is not None and ImageTk is not None:
            cache_key = ('png', int(target_width), str(self.scheme_png_path.resolve()))
            cached = self.scheme_render_cache.get(cache_key)
            if cached is not None:
                return cached
            try:
                image = Image.open(self.scheme_png_path)
                src_w, src_h = image.size
                scale = target_width / max(src_w, 1)
                target_height = max(1, int(src_h * scale))
                resized = image.resize((target_width, target_height), Image.LANCZOS)
                resized = self._overlay_component_state_on_image(resized)
                photo = ImageTk.PhotoImage(resized)
                result = (photo, resized.size)
                if len(self.scheme_render_cache) > 6:
                    self.scheme_render_cache.clear()
                self.scheme_render_cache[cache_key] = result
                return result
            except Exception:
                pass

        return None, None

    def _refresh_scheme_background(self, target_width=None):
        if not getattr(self, 'scheme_canvas', None):
            return
        if target_width is None:
            target_width = max(self.scheme_canvas.winfo_width(), 1191)
        photo, size = self._render_scheme_png(target_width)
        if photo is None:
            self.scheme_background_photo = None
            self.scheme_background_size = (max(target_width, 1191), 842)
            self.scheme_canvas.create_text(
                24,
                24,
                anchor='nw',
                text='Не удалось отрисовать SVG-схему.\nПроверь наличие pt80_exact_with_areas.svg или pt80_exact_with_areas.png рядом с main_gui.py.',
                fill='#a61e1e',
                font=('Segoe UI', 11, 'bold'),
            )
            return
        self.scheme_background_photo = photo
        self.scheme_background_size = size
        if self.scheme_background_item is None:
            self.scheme_background_item = self.scheme_canvas.create_image(0, 0, image=photo, anchor='nw')
        else:
            self.scheme_canvas.itemconfigure(self.scheme_background_item, image=photo)
        self.scheme_canvas.tag_lower(self.scheme_background_item)

    def _draw_component_badges(self):
        # Поверх SVG ничего не рисуем: схема должна отображаться полностью,
        # без закрывающих её плашек и белых прямоугольников.
        self.scheme_items = {}
        self.scheme_text_items = {}
    def _draw_scheme_legend(self):
        # Легенду на холсте не выводим, чтобы не перекрывать линии SVG.
        return
    def _redraw_scheme(self, event=None):
        if not hasattr(self, 'scheme_canvas'):
            return
        self.component_layout = self.load_component_layout()
        canvas = self.scheme_canvas
        canvas.delete('all')
        self.scheme_items = {}
        self.scheme_text_items = {}
        self.scheme_background_item = None
        self.scheme_background_photo = None
        root, refs = self._load_svg_tree()
        target_width = max(canvas.winfo_width(), 400)
        source_w = max(float(self.scheme_source_size[0]), 1.0)
        source_h = max(float(self.scheme_source_size[1]), 1.0)
        scale = target_width / source_w
        draw_width = max(1, int(round(source_w * scale)))
        draw_height = max(1, int(round(source_h * scale)))
        self.scheme_background_size = (draw_width, draw_height)
        canvas.config(scrollregion=(0, 0, draw_width, draw_height))
        if root is None:
            canvas.create_text(
                24,
                24,
                anchor='nw',
                text='Не удалось открыть SVG-схему\nПроверь наличие pt80_exact_with_areas.svg рядом с main_gui.py.',
                fill='#a61e1e',
                font=('Segoe UI', 11, 'bold'),
            )
            return
        render_state = self._build_scheme_state()
        base_matrix = (scale, 0.0, 0.0, scale, 0.0, 0.0)
        self._draw_svg_node(canvas, root, base_matrix, refs, render_state, inherited_paint=None, from_use=False)

    def collect_component_temperatures(self):
        if not self.results:
            return {}
        temps = {
            'cvd': self.last_params.get('fresh_steam_temp', t0) if self.last_params else t0,
            'csnd': ts(float(self.results.get('P_prom', 0.12))) if float(self.results.get('P_prom', 0.0)) > 0 else None,
            'generator': float(self.results.get('N_el_calc', self.results.get('Nz', 0.0))),
            'condenser': ts(float(self.results.get('P_k', 0.005))) if float(self.results.get('P_k', 0.0)) > 0 else None,
            'pvd7': ts(float(self.results.get('P1', 0.0))) if float(self.results.get('P1', 0.0)) > 0 else None,
            'pvd6': ts(float(self.results.get('P2', 0.0))) if float(self.results.get('P2', 0.0)) > 0 else None,
            'pvd5': ts(float(self.results.get('P3', 0.0))) if float(self.results.get('P3', 0.0)) > 0 else None,
            'pnd4': ts(float(self.results.get('P4', 0.0))) if float(self.results.get('P4', 0.0)) > 0 else None,
            'pnd3': ts(float(self.results.get('P5', 0.0))) if float(self.results.get('P5', 0.0)) > 0 else None,
            'pnd2': ts(float(self.results.get('P6', 0.0))) if float(self.results.get('P6', 0.0)) > 0 else None,
            'pnd1': ts(float(self.results.get('P7', 0.0))) if float(self.results.get('P7', 0.0)) > 0 else None,
            'deaerator': ts_d,
        }
        # ПСГ: поддерживаем оба варианта структуры результатов.
        if 'psv1' in self.results and isinstance(self.results.get('psv1'), dict):
            temps['psg1'] = self.results['psv1'].get('t_sat_c')
            temps['psg2'] = self.results['psv1'].get('t_water_out_c')
        else:
            if isinstance(self.results.get('psv_vto'), dict):
                temps['psg1'] = self.results['psv_vto'].get('t_sat_c')
            if isinstance(self.results.get('psv_nto'), dict):
                temps['psg2'] = self.results['psv_nto'].get('t_sat_c')
        return temps
    def _update_scheme_colors(self, refresh_background=True):
        if not getattr(self, 'scheme_canvas', None):
            return
        self._redraw_scheme()

    # ---------- Страница 2: Расчёт (краткие результаты) ----------
    def create_results_tab(self):
        frame = ttk.Frame(self.results_tab, padding=10)
        frame.pack(fill='both', expand=True)
        frame.rowconfigure(0, weight=2)
        frame.rowconfigure(1, weight=3)
        frame.columnconfigure(0, weight=1)
        # Верхняя часть: краткая таблица результатов
        summary_frame = ttk.LabelFrame(frame, text="Краткие результаты", padding=5)
        summary_frame.grid(row=0, column=0, sticky='nsew', pady=(0, 6))
        summary_frame.rowconfigure(0, weight=1)
        summary_frame.columnconfigure(0, weight=1)
        self.results_tree = ttk.Treeview(summary_frame, columns=('value', 'unit'), height=10, show='tree headings')
        self.results_tree.heading('#0', text='Параметр')
        self.results_tree.heading('value', text='Значение')
        self.results_tree.heading('unit', text='Единица')
        self.results_tree.column('#0', width=320)
        self.results_tree.column('value', width=170)
        self.results_tree.column('unit', width=100)
        self.results_tree.grid(row=0, column=0, sticky='nsew')
        summary_scroll = ttk.Scrollbar(summary_frame, orient='vertical', command=self.results_tree.yview)
        self.results_tree.configure(yscrollcommand=summary_scroll.set)
        summary_scroll.grid(row=0, column=1, sticky='ns')
        # Нижняя часть: подробная плашка расчёта с формулами и пояснениями
        details_frame = ttk.LabelFrame(frame, text="Плашка расчёта: формулы, подстановка и объяснения", padding=5)
        details_frame.grid(row=1, column=0, sticky='nsew')
        details_frame.rowconfigure(0, weight=1)
        details_frame.columnconfigure(0, weight=1)
        self.results_text = tk.Text(details_frame, wrap='word', font=('Courier New', 10), padx=8, pady=8)
        self.results_text.grid(row=0, column=0, sticky='nsew')
        details_scroll = ttk.Scrollbar(details_frame, orient='vertical', command=self.results_text.yview)
        self.results_text.configure(yscrollcommand=details_scroll.set)
        details_scroll.grid(row=0, column=1, sticky='ns')
        self.results_text.insert('1.0', 'После запуска расчёта здесь появится пошаговый вывод с формулами, подстановкой чисел и пояснениями.')
        self.results_text.config(state='disabled')
    def update_results_tab(self):
        if not self.results:
            return
        for item in self.results_tree.get_children():
            self.results_tree.delete(item)
        env_power = None
        if self.environment_context:
            env_power = self.environment_context.get('nz_env')
        data = [
            ("Nz (запрошенная электрическая мощность)", f"{self.results.get('Nz', 0):.1f}", "МВт"),
            ("N_el_calc (расчётная мощность генератора)", f"{self.results.get('N_el_calc', self.results.get('Nz', 0)):.2f}", "МВт"),
            ("N_env (мощность с поправкой на вакуум)", f"{env_power:.2f}" if env_power is not None else "—", "МВт"),
            ("G0 (расход свежего пара)", f"{self.results.get('G0', 0):.1f}", "т/ч"),
            ("Gк (в конденсатор)", f"{self.results.get('G_cond', 0):.1f}", "т/ч"),
            ("Q0 (производительность котла)", f"{self.results.get('Q0', 0):.1f}", "Гкал/ч"),
            ("eta_brut (КПД брутто)", f"{self.results.get('eta_brut', 0):.1f}", "%"),
            ("q_t (удельный расход тепла)", f"{self.results.get('q_t', 0):.0f}", "ккал/кВт·ч"),
            ("Pk (давление в конденсаторе)", f"{self.results.get('P_k', 0)*1000:.1f}", "кПа"),
            ("t_pv (температура питательной воды)", f"{self.results.get('t_pv', 0):.1f}", "°C"),
            ("t_ok (температура ОК после ПНД)", f"{self.results.get('t_ok', 0):.1f}", "°C"),
            ("Итераций", f"{self.results.get('iterations', 0)}", ""),
            ("Невязка баланса", f"{abs(self.results.get('delta_balance', 0)):.3f}", "т/ч"),
        ]
        for label, val, unit in data:
            self.results_tree.insert('', 'end', text=label, values=(val, unit))
        regime_warnings = self.results.get('regime_warnings') or []
        if self.results.get('t_regime_nmax_ref') is not None:
            self.results_tree.insert('', 'end', text='T-огибающая Nmax(Qтф)', values=(f"{float(self.results.get('t_regime_nmax_ref', 0.0)):.1f}", 'МВт'))
            self.results_tree.insert('', 'end', text='Запас до Т-границы', values=(f"{float(self.results.get('t_regime_n_margin_mw', 0.0)):.1f}", 'МВт'))
        if self.results.get('t_regime_g0_ref') is not None:
            self.results_tree.insert('', 'end', text='Ориентир G0 по карте', values=(f"{float(self.results.get('t_regime_g0_ref', 0.0)):.1f}", 'т/ч'))
        if self.results.get('G_to_csnd') is not None:
            self.results_tree.insert('', 'end', text='Расход на входе в ЦСНД', values=(f"{float(self.results.get('G_to_csnd', 0.0)):.1f}", 'т/ч'))
        status_txt = 'Допустим' if self.results.get('regime_valid', True) else 'Недопустим'
        self.results_tree.insert('', 'end', text='Статус режима', values=(status_txt, ''))
        self.results_text.config(state='normal')
        self.results_text.delete('1.0', 'end')
        report = self.build_calculation_report()
        regime_warnings = self.results.get('regime_warnings') or []
        if regime_warnings:
            header = ('ВНИМАНИЕ: РЕЖИМ ВХОДИТ В ОБЛАСТЬ ЕПД / НАРУШАЕТ ЭКСПЛУАТАЦИОННУЮ ОГИБАЮЩУЮ\n'
                      if not self.results.get('regime_valid', True)
                      else 'Предупреждения по режиму:\n')
            warn_text = '\n'.join(f' - {w}' for w in regime_warnings) + '\n\n'
            self.results_text.insert('1.0', header + warn_text + report)
        else:
            self.results_text.insert('1.0', report)
        self.results_text.config(state='disabled')
    @staticmethod
    def _kgs_to_tph(value_kg_s):
        return value_kg_s * 3.6
    @staticmethod
    def _safe_div(num, den):
        return num / den if abs(den) > 1e-9 else 0.0
    def _estimate_initial_g0_terms(self, nz, gprom, qtf, shema_tf):
        if nz <= 80:
            g0_base = 6.6 + 3.72 * nz
        else:
            g0_base = 6.6 + 3.72 * 80 + (nz - 80) * 4.5
        if gprom > 200:
            k_prom = 0.65
        elif gprom > 150:
            k_prom = 0.58
        elif gprom > 100:
            k_prom = 0.50
        elif gprom > 50:
            k_prom = 0.45
        else:
            k_prom = 0.40
        if shema_tf == 2:
            k_tf = 0.38 if qtf > 80 else 0.35 if qtf > 50 else 0.32
        else:
            k_tf = 0.32 if qtf > 80 else 0.28 if qtf > 50 else 0.25
        dg_prom = gprom * k_prom
        dg_tf = qtf * k_tf
        g0_initial = g0_base + dg_prom + dg_tf
        return {
            'g0_base': g0_base,
            'k_prom': k_prom,
            'k_tf': k_tf,
            'dg_prom': dg_prom,
            'dg_tf': dg_tf,
            'g0_initial': g0_initial,
        }
    def build_calculation_report(self):
        if not self.results:
            return "Нет данных расчёта."
        r = self.results
        p = self.last_params or {}
        env = self.environment_context or {}
        nz = float(r.get('Nz', 0.0))
        gprom = float(r.get('Gprom', 0.0))
        qtf = float(r.get('Qtf', 0.0))
        shema_tf = int(r.get('shema_tf', 1))
        g0 = float(r.get('G0', 0.0))
        n_cvd = float(r.get('N_cvd', 0.0))
        n_csnd = float(r.get('N_csnd', 0.0))
        n_el_calc = float(r.get('N_el_calc', r.get('Nz', 0.0)))
        p_k = float(r.get('P_k', 0.0))
        t_pv = float(r.get('t_pv', 0.0))
        g1 = float(r.get('G1', 0.0))
        g2 = float(r.get('G2', 0.0))
        g3 = float(r.get('G3', 0.0))
        g4 = float(r.get('G4', 0.0))
        g5 = float(r.get('G5', 0.0))
        g6 = float(r.get('G6', 0.0))
        g7 = float(r.get('G7', 0.0))
        g_steam_d = float(r.get('G_steam_d', 0.0))
        g_vto = float(r.get('G_vto', 0.0))
        g_nto = float(r.get('G_nto', 0.0))
        g_cond = float(r.get('G_cond', 0.0))
        g_extract = g1 + g2 + g3 + g4 + g5 + g6 + g7 + g_steam_d + gprom + g_vto + g_nto
        g_cond_balance = g0 - g_extract
        # Энтальпии и тепловой поток
        h0 = h_steam(P0, t0)
        h_pv = h_water_temp(t_pv)
        q0_kw = g0 * 1000.0 / 3600.0 * (h0 - h_pv)
        q0_gcal = q0_kw / 1163.0
        eta_brut_calc = self._safe_div(nz * 1000.0, q0_kw) * 100.0
        q_t_calc = self._safe_div(q0_kw, nz * 1000.0) * 3600.0 / 4.19
        # Теплофикационные отборы по фактическим давлениям
        p_vto = float(r.get('P_vto', 0.0))
        p_nto = float(r.get('P_nto', 0.0))
        r_nto = h_steam_sat(p_nto) - h_water(p_nto) if p_nto > 0 else 0.0
        r_vto = h_steam_sat(p_vto) - h_water(p_vto) if p_vto > 0 else 0.0
        qtf_kw = qtf * 1163.0
        if shema_tf == 1:
            g_nto_formula = self._kgs_to_tph(self._safe_div(qtf_kw, r_nto)) if r_nto > 0 else 0.0
            g_vto_formula = 0.0
        else:
            g_vto_formula = self._kgs_to_tph(self._safe_div(0.6 * qtf_kw, r_vto)) if r_vto > 0 else 0.0
            g_nto_formula = self._kgs_to_tph(self._safe_div(0.4 * qtf_kw, r_nto)) if r_nto > 0 else 0.0
        g0_terms = self._estimate_initial_g0_terms(nz, gprom, qtf, shema_tf)
        t_sat_cond = ts(p_k) if p_k > 0 else 0.0
        pk_env = env.get('pk_env')
        nz_env = env.get('nz_env')
        t_water = env.get('t_water')
        lines = []
        add = lines.append
        add("════════════════════════════════════════════════════════════════════")
        add("            ПОШАГОВЫЙ ВЫВОД РАСЧЁТА РЕЖИМА ПТ-80")
        add("════════════════════════════════════════════════════════════════════")
        add("")
        add("1. ИСХОДНЫЕ ДАННЫЕ")
        add("────────────────────────────────────────────────────────────────────")
        add(f"  Nz     = {nz:.2f} МВт")
        add(f"  Gprom  = {gprom:.2f} т/ч")
        add(f"  Qtf    = {qtf:.2f} Гкал/ч")
        add(f"  Схема  = {'одноступенчатая' if shema_tf == 1 else 'двухступенчатая'}")
        if p:
            add(f"  t_air  = {float(p.get('t_air', 0.0)):.1f} °C")
            add(f"  Цена топлива = {float(p.get('fuel_price', 0.0)):.0f} руб/т у.т.")
        add("")
        add("2. НАЧАЛЬНОЕ ПРИБЛИЖЕНИЕ ПО РАСХОДУ СВЕЖЕГО ПАРА")
        add("────────────────────────────────────────────────────────────────────")
        add("  Формула из модели:")
        add("    G0_нач = G0_баз + ΔGпром + ΔGтф")
        add("    G0_баз = 6.6 + 3.72·Nz        (для Nz ≤ 80 МВт)")
        add("    ΔGпром = kпром·Gprom")
        add("    ΔGтф   = kтф·Qtf")
        add("")
        add("  Подстановка:")
        add(f"    G0_баз = 6.6 + 3.72·{nz:.2f} = {g0_terms['g0_base']:.2f} т/ч")
        add(f"    ΔGпром = {g0_terms['k_prom']:.2f}·{gprom:.2f} = {g0_terms['dg_prom']:.2f} т/ч")
        add(f"    ΔGтф   = {g0_terms['k_tf']:.2f}·{qtf:.2f} = {g0_terms['dg_tf']:.2f} т/ч")
        add(f"    G0_нач = {g0_terms['g0_initial']:.2f} т/ч")
        add(f"    G0_итог после итераций = {g0:.2f} т/ч")
        add("  Пояснение: начальное значение берётся по эксплуатационной характеристике,")
        add("  затем модель итерационно подстраивает G0, чтобы сойтись по мощности и балансу.")
        add("")
        add("3. ТЕПЛОФИКАЦИЯ И РАСХОДЫ НА ТЕПЛОВЫЕ ОТБОРЫ")
        add("────────────────────────────────────────────────────────────────────")
        add("  Перевод тепловой нагрузки:")
        add(f"    Qtf_кВт = {qtf:.2f} · 1163 = {qtf_kw:.2f} кВт")
        if shema_tf == 1:
            add("  Одноступенчатая схема:")
            add("    Gнто = Qtf_кВт / rнто")
            add(f"    rнто = h''(Pнто) - h'(Pнто) = {r_nto:.2f} кДж/кг")
            add(f"    Gнто = {qtf_kw:.2f} / {r_nto:.2f} · 3.6 = {g_nto_formula:.2f} т/ч")
            add(f"    В расчёте принято: Gнто = {g_nto:.2f} т/ч")
        else:
            add("  Двухступенчатая схема:")
            add("    Gвто = 0.6·Qtf_кВт / rвто")
            add("    Gнто = 0.4·Qtf_кВт / rнто")
            add(f"    rвто = {r_vto:.2f} кДж/кг, rнто = {r_nto:.2f} кДж/кг")
            add(f"    Gвто = 0.6·{qtf_kw:.2f} / {r_vto:.2f} · 3.6 = {g_vto_formula:.2f} т/ч")
            add(f"    Gнто = 0.4·{qtf_kw:.2f} / {r_nto:.2f} · 3.6 = {g_nto_formula:.2f} т/ч")
            add(f"    В расчёте принято: Gвто = {g_vto:.2f} т/ч, Gнто = {g_nto:.2f} т/ч")
        add("  Пояснение: тепловая нагрузка отбирает часть пара из турбины и тем самым")
        add("  снижает доступный перепад энтальпии на электрическую мощность.")
        add("")
        add("4. МОЩНОСТЬ ПО ЦИЛИНДРАМ И ЭЛЕКТРИЧЕСКИЙ РЕЗУЛЬТАТ")
        add("────────────────────────────────────────────────────────────────────")
        add("  Формула:")
        add("    Nэл = (Nцвд + Nцснд) · ηмех · ηген")
        add("  Подстановка:")
        add(f"    Nэл = ({n_cvd:.2f} + {n_csnd:.2f}) · {etam:.3f} · {etag_nom:.3f} = {n_el_calc:.2f} МВт")
        add(f"    Целевая мощность Nz = {nz:.2f} МВт")
        add(f"    Отклонение = {n_el_calc - nz:+.2f} МВт")
        add("  Пояснение: ЦВД даёт основную часть мощности до промперегрева, ЦСНД —")
        add("  после промперегрева с учётом регенерации, теплофикации и хвоста конденсации.")
        add("")
        add("5. БАЛАНС ПАРА")
        add("────────────────────────────────────────────────────────────────────")
        add("  Контрольная формула:")
        add("    G0 = G1+G2+G3+G4+G5+G6+G7+Gsteam_d+Gprom+Gвто+Gнто+Gк")
        add("  Подстановка:")
        add(f"    Gотборов = {g1:.2f}+{g2:.2f}+{g3:.2f}+{g4:.2f}+{g5:.2f}+{g6:.2f}+{g7:.2f}+{g_steam_d:.2f}+{gprom:.2f}+{g_vto:.2f}+{g_nto:.2f}")
        add(f"             = {g_extract:.2f} т/ч")
        add(f"    Gк(по балансу) = {g0:.2f} - {g_extract:.2f} = {g_cond_balance:.2f} т/ч")
        add(f"    Gк(в результатах) = {g_cond:.2f} т/ч")
        add(f"    Невязка баланса = {abs(float(r.get('delta_balance', 0.0))):.3f} т/ч")
        add("  Пояснение: маленькая невязка означает, что массовый баланс схемы сошёлся.")
        add("")
        add("6. КОНДЕНСАТОР, ВАКУУМ И ВЛИЯНИЕ ВНЕШНИХ УСЛОВИЙ")
        add("────────────────────────────────────────────────────────────────────")
        add(f"  Фактическое давление в конденсаторе: Pк = {p_k*1000.0:.2f} кПа")
        add(f"  Температура насыщения при этом давлении: ts(Pк) = {t_sat_cond:.2f} °C")
        if t_water is not None and pk_env is not None:
            add(f"  Оценка по температуре наружного воздуха: tв1 ≈ {float(t_water):.2f} °C")
            add(f"  Ожидаемое давление конденсатора по среде: Pк,среды ≈ {float(pk_env):.2f} кПа")
        if nz_env is not None:
            add(f"  Мощность с поправкой на вакуум/среду: Nenv ≈ {float(nz_env):.2f} МВт")
        add("  Пояснение: рост Pк ухудшает вакуум, увеличивает потери хвоста и обычно")
        add("  приводит к недовыработке мощности и росту удельного расхода тепла.")
        add("")
        add("7. КОТЁЛ, ПИТАТЕЛЬНАЯ ВОДА И УДЕЛЬНЫЕ ПОКАЗАТЕЛИ")
        add("────────────────────────────────────────────────────────────────────")
        add("  Формулы:")
        add("    Q0_кВт = G0 · 1000/3600 · (h0 - hпв)")
        add("    Q0_Гкал/ч = Q0_кВт / 1163")
        add("    ηбрут = Nz·1000 / Q0_кВт · 100%")
        add("    qт = Q0_кВт / (Nz·1000) · 3600 / 4.19")
        add("  Подстановка:")
        add(f"    h0  = h(P0={P0:.2f} МПа, t0={t0:.1f} °C) = {h0:.2f} кДж/кг")
        add(f"    hпв = h(tпв={t_pv:.1f} °C) = {h_pv:.2f} кДж/кг")
        add(f"    Q0_кВт = {g0:.2f}·1000/3600·({h0:.2f}-{h_pv:.2f}) = {q0_kw:.2f} кВт")
        add(f"    Q0_Гкал/ч = {q0_kw:.2f} / 1163 = {q0_gcal:.2f} Гкал/ч")
        add(f"    ηбрут = {nz:.2f}·1000 / {q0_kw:.2f} · 100 = {eta_brut_calc:.2f} %")
        add(f"    qт = {q0_kw:.2f} / ({nz:.2f}·1000) · 3600 / 4.19 = {q_t_calc:.2f} ккал/кВт·ч")
        add(f"    В таблице результатов: Q0 = {float(r.get('Q0', 0.0)):.2f} Гкал/ч, ηбрут = {float(r.get('eta_brut', 0.0)):.2f} %, qт = {float(r.get('q_t', 0.0)):.2f} ккал/кВт·ч")
        add("  Пояснение: чем выше температура питательной воды, тем меньше тепла нужно")
        add("  в котле на тот же расход пара, а значит выше экономичность установки.")
        add("")
        add("8. КРАТКИЙ ИНЖЕНЕРНЫЙ ВЫВОД")
        add("────────────────────────────────────────────────────────────────────")
        add(f"  • Режим сошёлся за {int(r.get('iterations', 0))} итерац.")
        add(f"  • Свежий пар G0 = {g0:.2f} т/ч обеспечивает около {n_el_calc:.2f} МВт расчётной мощности.")
        add(f"  • В конденсатор уходит Gк = {g_cond:.2f} т/ч при Pк = {p_k*1000.0:.2f} кПа.")
        add(f"  • Питательная вода после регенерации имеет tпв = {t_pv:.1f} °C, что влияет на Q0 и qт.")
        add("  • Плашка расчёта показывает не только итог, но и логику: от исходных данных")
        add("    к расходу свежего пара, отборам, мощности, вакууму и тепловой экономичности.")
        return "\n".join(lines)
    # ---------- Страница 3: Компоненты (детальные параметры) ----------
    def create_components_tab(self):
        """Создаёт вкладку с прокруткой, содержащую все компоненты"""
        canvas = tk.Canvas(self.components_tab)
        scrollbar = ttk.Scrollbar(self.components_tab, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.components_frames = {}  # для хранения деревьев
        # Создаём фреймы для каждой группы компонентов
        component_groups = [
            ("Основные компоненты", ["cvd", "csnd", "condenser"]),
            ("Регенерация ВД", ["pvd7", "pvd6", "pvd5"]),
            ("Деаэратор и НД", ["deaerator", "pnd_group"]),
            ("Тепловая сеть и Генератор", ["heat_network", "generator", "psv"]),  # <-- ДОБАВЛЕН "psv"
            ("Общие показатели", ["overall"]),
        ]
        for group_name, component_ids in component_groups:
            # Заголовок группы
            ttk.Label(scrollable_frame, text=f"▼ {group_name}", font=('Arial', 11, 'bold')).pack(anchor='w', pady=(10,5))
            # Контейнер для компонентов в группе (два столбца)
            group_container = ttk.Frame(scrollable_frame)
            group_container.pack(fill='both', expand=True, padx=5)
            group_container.columnconfigure(0, weight=1)
            group_container.columnconfigure(1, weight=1)
            for idx, comp_id in enumerate(component_ids):
                col = idx % 2
                row = idx // 2
                self._create_component_frame(group_container, comp_id, row, col)
    def _create_component_frame(self, parent, comp_id, row, col):
        """Создаёт фрейм для одного компонента с таблицей"""
        frame = ttk.LabelFrame(parent, text=f"⚙️ {comp_id}", padding=5)
        frame.grid(row=row, column=col, sticky='nsew', padx=3, pady=3)
        tree = ttk.Treeview(frame, columns=('value', 'unit'), height=6, show='tree headings')
        tree.heading('#0', text='Параметр')
        tree.heading('value', text='Значение')
        tree.heading('unit', text='Единица')
        tree.column('#0', width=200)
        tree.column('value', width=100)
        tree.column('unit', width=70)
        tree.pack(fill='both', expand=True)
        self.components_frames[comp_id] = {'frame': frame, 'tree': tree}
    def update_components_tab(self):
        """Обновляет данные на вкладке Компоненты, используя self.results['components']"""
        if not self.results or 'components' not in self.results:
            return
        comp_data = self.results['components']
        for comp_id, data in comp_data.items():
            if comp_id not in self.components_frames:
                continue
            tree = self.components_frames[comp_id]['tree']
            frame = self.components_frames[comp_id]['frame']
            # Очистить
            for item in tree.get_children():
                tree.delete(item)
            # Обновить заголовок
            name = data.get('name', comp_id)
            frame.configure(text=f"⚙️ {name}")
            # Заполнить
            for param in data.get('data', []):
                if len(param) == 3:
                    tree.insert('', 'end', text=param[0], values=(param[1], param[2]))
        # Дополнительно заполняем данные для ПСВ, если они есть в self.results (не в components)
        if 'psv' in self.components_frames and ('psv1' in self.results or 'psv_nto' in self.results):
            tree = self.components_frames['psv']['tree']
            frame = self.components_frames['psv']['frame']
            for item in tree.get_children():
                tree.delete(item)
            frame.configure(text="⚙️ ПСВ (подогреватели сетевой воды)")
            scheme = self.results.get('shema_tf', 1)
            if scheme == 1:
                psv1 = self.results.get('psv1', {})
                items = [
                    ("Расход сетевой воды G_water", f"{self.results.get('G_water_tph', 0):.1f}", "т/ч"),
                    ("Температура воды на входе", f"{self.results.get('t_water_in_c', 0):.1f}", "°C"),
                    ("Температура воды на выходе", f"{psv1.get('t_water_out_c', 0):.1f}", "°C"),
                    ("Расход пара на ПСВ", f"{psv1.get('G_steam_tph', 0):.2f}", "т/ч"),
                    ("Давление пара", f"{psv1.get('P_steam_mpa', 0):.3f}", "МПа"),
                ]
            else:
                psv_nto = self.results.get('psv_nto', {})
                psv_vto = self.results.get('psv_vto', {})
                items = [
                    ("Расход сетевой воды G_water", f"{self.results.get('G_water_tph', 0):.1f}", "т/ч"),
                    ("Температура воды на входе", f"{self.results.get('t_water_in_c', 0):.1f}", "°C"),
                    ("--- НТО (нижний) ---", "", ""),
                    ("  Температура после НТО", f"{psv_nto.get('t_water_out_c', 0):.1f}", "°C"),
                    ("  Расход пара на НТО", f"{psv_nto.get('G_steam_tph', 0):.2f}", "т/ч"),
                    ("  Давление пара НТО", f"{psv_nto.get('P_steam_mpa', 0):.3f}", "МПа"),
                    ("--- ВТО (верхний) ---", "", ""),
                    ("  Температура после ВТО", f"{psv_vto.get('t_water_out_c', 0):.1f}", "°C"),
                    ("  Расход пара на ВТО", f"{psv_vto.get('G_steam_tph', 0):.2f}", "т/ч"),
                    ("  Давление пара ВТО", f"{psv_vto.get('P_steam_mpa', 0):.3f}", "МПа"),
                    ("Итоговый нагрев", f"{self.results.get('delta_t_total_c', 0):.1f}", "°C"),
                ]
            for label, val, unit in items:
                tree.insert('', 'end', text=label, values=(val, unit))
    # ---------- Страница 4: Формулы ----------
    def create_formulas_tab(self):
        frame = ttk.Frame(self.formulas_tab)
        frame.pack(fill='both', expand=True, padx=5, pady=5)
        text_frame = ttk.Frame(frame)
        text_frame.pack(fill='both', expand=True)
        scrollbar = ttk.Scrollbar(text_frame)
        scrollbar.pack(side='right', fill='y')
        text_widget = tk.Text(text_frame, wrap='word', yscrollcommand=scrollbar.set, font=('Courier', 9))
        scrollbar.config(command=text_widget.yview)
        text_widget.pack(side='left', fill='both', expand=True)
        formulas_content = """\
════════════════════════════════════════════════════════════════════════════════
                    ФОРМУЛЫ РАСЧЕТА МОДЕЛИ ПТ-80 ТЭЦ
════════════════════════════════════════════════════════════════════════════════
1. НАЧАЛЬНОЕ ПРИБЛИЖЕНИЕ РАСХОДА СВЕЖЕГО ПАРА
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   G₀,нач = G₀,баз + kпром·Gprom + kтф·Qtf
   G₀,баз = 6.6 + 3.72·Nz   (для диапазона до 80 МВт)
   где:
   - Nz - запрос электрической мощности, МВт
   - Gprom - производственный отбор, т/ч
   - Qtf - тепловая нагрузка, Гкал/ч
2. РАСЧЕТ ДАВЛЕНИЙ В ЦВД
━━━━━━━━━━━━━━━━━━━━━━━━
   P₁ = f(G₀) - давление в отборе 1 (ПВД-7)
   P₂ = f(G₀, G₁) - давление в отборе 2 (ПВД-6)
   P₃ = f(G₀, G₁, G₂) - давление в отборе 3 (ПВД-5)
   Pпром = f(G₀, G₁, G₂, G₃) - давление на выходе ЦВД
3. РАСЧЕТ ДАВЛЕНИЙ В ЦСНД
━━━━━━━━━━━━━━━━━━━━━━━━━
   P₄, P₅, P₆, P₇ - давления в отборах на ПНД
   PВТО, PНТО - давления теплофикационных отборов
   Pк - давление в конденсаторе
4. РАСЧЕТ МОЩНОСТИ
━━━━━━━━━━━━━━━━━━
   N_ЦВД = ΣΔh_i * G_i
   N_ЦСНД = ΣΔh_j * G_j
   N_эл = (N_ЦВД + N_ЦСНД) * ηмех * ηген
   при этом давление в конденсаторе Pк влияет на хвостовую мощность ЦСНД
5. ТЕПЛОФИКАЦИЯ
━━━━━━━━━━━━━━
   Одноступенчатая: G_НТО = Qтф / (h_НТО - h_к)
   Двухступенчатая: G_ВТО = 0.6*Qтф / (h_ВТО - h_к), G_НТО = 0.4*Qтф / (h_НТО - h_к)
6. БАЛАНС ПАРА
━━━━━━━━━━━━━
   G₀ = G₁ + G₂ + G₃ + G₄ + G₅ + G₆ + G₇ + G_steam_d + Gprom + G_ВТО + G_НТО + Gк
7. ИТЕРАЦИОННЫЙ ЦИКЛ
━━━━━━━━━━━━━━━━━━━
   До сходимости по мощности и балансу (макс. 15 итераций)
   Контроль: недовыработка по вакууму, Gк, Q0, qт, ηбрут
════════════════════════════════════════════════════════════════════════════════
"""
        text_widget.insert('1.0', formulas_content)
        text_widget.config(state='disabled')
    # ---------- Страница 5: Экономика ----------
    def create_economics_tab(self):
        self.econ_canvas_frame = ttk.Frame(self.economics_tab)
        self.econ_canvas_frame.pack(fill='both', expand=True, padx=5, pady=5)
    def update_economics_graph(self):
        for child in self.econ_canvas_frame.winfo_children():
            child.destroy()
        if self.optimum and 'curve' in self.optimum:
            fig = plot_power_vs_profit(self.optimum['curve'])
            canvas = FigureCanvasTkAgg(fig, master=self.econ_canvas_frame)
            canvas.draw()
            canvas.get_tk_widget().pack(fill='both', expand=True)
    # ---------- Страница 6: Графики ----------
    def create_plots_tab(self):
        frame = ttk.Frame(self.plots_tab)
        frame.pack(fill='both', expand=True)
        control_frame = ttk.Frame(frame)
        control_frame.pack(fill='x', pady=5)
        ttk.Label(control_frame, text="Выберите график:").pack(side='left', padx=5)
        self.plot_choice = tk.StringVar()
        self.plot_combo = ttk.Combobox(control_frame, textvariable=self.plot_choice, state='readonly', width=50)
        self.plot_combo['values'] = [
            "Мощность → расход свежего пара",
            "Тепловая нагрузка → электрическая мощность",
            "Мощность → прибыль",
            "Час суток → рекомендуемая заявка РСВ",
            "Температура воздуха → давление конденсатора",
            "Давления по тракту ЦСНД",
            "h-s диаграмма (точки отборов)",
            "Структура баланса пара",
            "Структура регенерации",
            "Себестоимость и маржа по мощности"
        ]
        self.plot_combo.pack(side='left', padx=5)
        self.plot_combo.bind('<<ComboboxSelected>>', self.update_plot)
        self.plot_combo.current(0)
        self.plot_frame = ttk.Frame(frame)
        self.plot_frame.pack(fill='both', expand=True)
    def update_plot(self, event=None):
        for child in self.plot_frame.winfo_children():
            child.destroy()
        if not self.results:
            lbl = ttk.Label(self.plot_frame, text="Сначала выполните расчёт")
            lbl.pack()
            return
        choice = self.plot_choice.get()
        fig = None
        if choice == "Мощность → расход свежего пара" and self.power_steam_data:
            fig = plot_power_vs_steam(*self.power_steam_data)
        elif choice == "Тепловая нагрузка → электрическая мощность" and self.heat_power_data:
            fig = plot_heat_vs_power(*self.heat_power_data)
        elif choice == "Мощность → прибыль" and self.optimum:
            fig = plot_power_vs_profit(self.optimum['curve'])
        elif choice == "Час суток → рекомендуемая заявка РСВ" and self.schedule is not None:
            fig = plot_hourly_bid(self.schedule['table'])
        elif choice == "Температура воздуха → давление конденсатора" and self.temp_pressure_data:
            fig = plot_temp_vs_pressure(*self.temp_pressure_data)
        elif choice == "Давления по тракту ЦСНД" and self.csnd_pressures:
            fig = plot_csnd_pressures(*self.csnd_pressures)
        elif choice == "h-s диаграмма (точки отборов)" and self.hs_points:
            fig = plot_hs_diagram(self.hs_points)
        elif choice == "Структура баланса пара" and self.balance:
            fig = plot_steam_balance(self.balance)
        elif choice == "Структура регенерации" and self.regen_rows:
            fig = plot_regeneration_structure(self.regen_rows)
        elif choice == "Себестоимость и маржа по мощности" and self.optimum:
            fig = plot_cost_margin(self.optimum['curve'])
        if fig:
            canvas = FigureCanvasTkAgg(fig, master=self.plot_frame)
            canvas.draw()
            canvas.get_tk_widget().pack(fill='both', expand=True)
        else:
            lbl = ttk.Label(self.plot_frame, text="Данные для графика не подготовлены")
            lbl.pack()
    # ---------- Основной расчёт ----------
    def run_calculation(self):
        try:
            params = {key: var.get() for key, var in self.input_vars.items()}
            params['shema_tf'] = int(params['shema_tf'])
        except Exception as e:
            messagebox.showerror("Ошибка ввода", f"Проверьте числа:\n{str(e)}")
            return
        boiler_eff = 0.92
        mode_data = {
            "mode_id": "USER",
            "Nz": params['Nz'],
            "Gprom": params['Gprom'],
            "Qtf": params['Qtf'],
            "shema_tf": params['shema_tf'],
            "component_health": self.collect_component_health(),
        }
        try:
            self.last_params = params.copy()
            calc = run_mode_calculation(mode_data)
            self.results = calc['results']
            # Добавляем расчёт ПСВ
            t_water_in = float(self.results.get('t_water_in', 50.0))
            g_water_psg = self.results.get('G_water_psg', None)
            psg_results = calc_psg(params['Qtf'], params['shema_tf'], t_water_in=t_water_in, G_water=g_water_psg)
            self.results.update(psg_results)
            t_water = air_to_water_temp(params['t_air'])
            pk_env = condenser_pressure_from_water_temp(t_water)
            nz_env = environmental_power_correction(float(self.results["Nz"]), float(self.results["P_k"]) * 1000.0, pk_env)
            self.environment_context = {
                't_water': t_water,
                'pk_env': pk_env,
                'nz_env': nz_env,
            }
            self.regen_rows = build_regeneration_view(self.results)['rows']
            self.balance = calculate_station_steam_balance(self.results)
            self.limits = evaluate_limits(
                power_mw=nz_env,
                steam_flow_tph=float(self.results["G0"]),
                condenser_kpa=pk_env,
                fresh_steam_temp_c=params['fresh_steam_temp'],
                tech_limit_mw=params['tech_limit_mw'],
            )
            self.eco = calculate_economics_from_results(self.results, boiler_eff, params['fuel_price'])
            self.optimum = optimize_load_by_profit(
                gprom=params['Gprom'],
                qtf=params['Qtf'],
                shema_tf=params['shema_tf'],
                t_air=params['t_air'],
                boiler_eff=boiler_eff,
                fuel_price=params['fuel_price'],
                market_price=params['market_price'],
                tech_limit_mw=params['tech_limit_mw'],
                fresh_steam_temp_c=params['fresh_steam_temp'],
            )
            self.schedule = build_day_ahead_schedule(
                gprom=params['Gprom'],
                qtf=params['Qtf'],
                shema_tf=params['shema_tf'],
                base_air_temp=params['t_air'],
                boiler_eff=boiler_eff,
                fuel_price=params['fuel_price'],
                market_price=params['market_price'],
                tech_limit_mw=params['tech_limit_mw'],
                fresh_steam_temp_c=params['fresh_steam_temp'],
            )
            # Подготовка данных для графиков
            self.prepare_additional_plots(params, boiler_eff, t_water, pk_env)
            # Обновление всех страниц
            self.update_results_tab()
            self.update_components_tab()
            self.refresh_health_panel()
            self._update_scheme_colors()
            if hasattr(self, 'econ_canvas_frame'):
                self.update_economics_graph()
            if hasattr(self, 'plot_frame'):
                self.update_plot()
            # Переключение на вкладку Расчёт
            self.notebook.select(self.results_tab)
            regime_warnings = self.results.get('regime_warnings') or []
            if regime_warnings:
                title = 'Недопустимый режим' if not self.results.get('regime_valid', True) else 'Предупреждение по режиму'
                messagebox.showwarning(title, '\n'.join(regime_warnings))
        except Exception as e:
            messagebox.showerror("Ошибка расчёта", str(e))
            import traceback
            traceback.print_exc()
    def prepare_additional_plots(self, params, boiler_eff, t_water, pk_env):
        # Мощность → расход свежего пара
        power_range = list(range(40, 101, 5))
        g0_list = []
        for p in power_range:
            md = {"mode_id": f"PLOT-{p}", "Nz": float(p), "Gprom": params['Gprom'], "Qtf": params['Qtf'], "shema_tf": params['shema_tf']}
            try:
                c = run_mode_calculation(md)
                g0_list.append(c['results']['G0'])
            except Exception:
                g0_list.append(float('nan'))
        self.power_steam_data = (power_range, g0_list)
        # Тепловая нагрузка → электрическая мощность
        qtf_range = np.linspace(0, 100, 11)
        power_for_heat = []
        for q in qtf_range:
            md = {"mode_id": f"HEAT-{q:.0f}", "Nz": params['Nz'], "Gprom": params['Gprom'], "Qtf": q, "shema_tf": params['shema_tf']}
            try:
                c = run_mode_calculation(md)
                t_water_cur = air_to_water_temp(params['t_air'])
                pk_env_cur = condenser_pressure_from_water_temp(t_water_cur)
                nz_env_cur = environmental_power_correction(float(c['results']["Nz"]), float(c['results']["P_k"]) * 1000.0, pk_env_cur)
                power_for_heat.append(nz_env_cur)
            except Exception:
                power_for_heat.append(float('nan'))
        self.heat_power_data = (qtf_range, power_for_heat)
        # Температура воздуха → давление конденсатора
        temp_range = list(range(-30, 41, 5))
        press_range = [condenser_pressure_from_water_temp(air_to_water_temp(t)) for t in temp_range]
        self.temp_pressure_data = (temp_range, press_range)
        # Давления ЦСНД
        self.csnd_pressures = (
            self.results.get('P_vto', 0.12),
            self.results.get('P_nto', 0.09),
            self.results.get('P_k', 0.0045)
        )
        # h-s точки (примерные)
        hs_points = [
            (3500, 6.5, "Перед турбиной"),
            (3000, 6.2, "После ЦВД"),
            (2500, 6.5, "Конденсатор"),
        ]
        self.hs_points = hs_points
    # ---------- Страница 7: Динамика ----------
    def create_dynamic_tab(self):
        frame = ttk.Frame(self.dynamic_tab, padding=8)
        frame.pack(fill='both', expand=True)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(1, weight=1)
        frame.rowconfigure(2, weight=1)
        controls = ttk.LabelFrame(frame, text="Параметры переходного процесса", padding=8)
        controls.grid(row=0, column=0, sticky='ew', pady=(0, 6))
        controls.columnconfigure(1, weight=1)
        controls.columnconfigure(3, weight=1)
        controls.columnconfigure(5, weight=1)
        ttk.Label(controls, text="Сценарий").grid(row=0, column=0, sticky='w', padx=(0, 6), pady=2)
        self.dynamic_tab_scenario_combo = ttk.Combobox(
            controls,
            textvariable=self.dynamic_scenario_var,
            state='readonly',
            values=self.dynamic_scenario_labels,
            width=42,
        )
        self.dynamic_tab_scenario_combo.grid(row=0, column=1, sticky='ew', pady=2)
        if self.dynamic_scenario_labels:
            self.dynamic_tab_scenario_combo.current(0)
        ttk.Label(controls, text="Горизонт, с").grid(row=0, column=2, sticky='w', padx=(12, 6), pady=2)
        ttk.Entry(controls, textvariable=self.dynamic_t_end_var, width=10).grid(row=0, column=3, sticky='w', pady=2)
        ttk.Label(controls, text="Точек").grid(row=0, column=4, sticky='w', padx=(12, 6), pady=2)
        ttk.Entry(controls, textvariable=self.dynamic_n_points_var, width=10).grid(row=0, column=5, sticky='w', pady=2)
        self.dynamic_run_button = ttk.Button(controls, text="Запустить переходный процесс", command=self.run_dynamic_calculation)
        self.dynamic_run_button.grid(row=0, column=6, sticky='e', padx=(12, 0), pady=2)
        if run_dynamic_simulation is None:
            self.dynamic_run_button.state(['disabled'])
        summary_frame = ttk.LabelFrame(frame, text="Сводка", padding=5)
        summary_frame.grid(row=1, column=0, sticky='nsew', pady=(0, 6))
        summary_frame.columnconfigure(0, weight=1)
        summary_frame.rowconfigure(0, weight=0)
        summary_frame.rowconfigure(1, weight=1)
        summary_frame.rowconfigure(2, weight=1)
        self.dynamic_summary_text = tk.Text(summary_frame, height=7, wrap='word', font=('Courier New', 10))
        self.dynamic_summary_text.grid(row=0, column=0, columnspan=2, sticky='ew')
        self.dynamic_summary_text.insert('1.0', 'Нет данных динамического расчёта.')
        self.dynamic_summary_text.config(state='disabled')
        table_frame = ttk.LabelFrame(summary_frame, text='Временной ряд', padding=5)
        table_frame.grid(row=1, column=0, sticky='nsew', pady=(6, 0), padx=(0, 6))
        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)
        self.dynamic_table_columns = [
            't', 'N_el_actual', 'Nz_set', 'Ne_load', 'G0', 'G_cond',
            'G_vto', 'G_nto', 'P_prom', 'P_vto', 'P_nto', 'P_k', 'omega', 'delta_balance'
        ]
        self.dynamic_tree = ttk.Treeview(table_frame, columns=self.dynamic_table_columns, show='headings', height=14)
        for col in self.dynamic_table_columns:
            self.dynamic_tree.heading(col, text=col)
            self.dynamic_tree.column(col, width=92, anchor='center')
        self.dynamic_tree.grid(row=0, column=0, sticky='nsew')
        dyn_y = ttk.Scrollbar(table_frame, orient='vertical', command=self.dynamic_tree.yview)
        dyn_x = ttk.Scrollbar(table_frame, orient='horizontal', command=self.dynamic_tree.xview)
        self.dynamic_tree.configure(yscrollcommand=dyn_y.set, xscrollcommand=dyn_x.set)
        dyn_y.grid(row=0, column=1, sticky='ns')
        dyn_x.grid(row=1, column=0, sticky='ew')
        plot_frame = ttk.LabelFrame(summary_frame, text='График', padding=5)
        plot_frame.grid(row=1, column=1, sticky='nsew', pady=(6, 0))
        plot_frame.rowconfigure(1, weight=1)
        plot_frame.columnconfigure(0, weight=1)
        plot_controls = ttk.Frame(plot_frame)
        plot_controls.grid(row=0, column=0, sticky='ew', pady=(0, 6))
        ttk.Label(plot_controls, text='Показывать:').pack(side='left', padx=(0, 6))
        self.dynamic_plot_combo = ttk.Combobox(
            plot_controls,
            textvariable=self.dynamic_plot_choice,
            state='readonly',
            values=['Мощность', 'Расходы', 'Давления', 'Ротор', 'Баланс'],
            width=22,
        )
        self.dynamic_plot_combo.pack(side='left')
        self.dynamic_plot_combo.bind('<<ComboboxSelected>>', self.update_dynamic_plot)
        self.dynamic_plot_combo.current(0)
        self.dynamic_plot_frame = ttk.Frame(plot_frame)
        self.dynamic_plot_frame.grid(row=1, column=0, sticky='nsew')
    def _get_dynamic_selected_key(self):
        label = self.dynamic_scenario_var.get().strip()
        return self.dynamic_scenario_map.get(label, label)
    def _build_dynamic_base_mode(self):
        params = {key: var.get() for key, var in self.input_vars.items()}
        params['shema_tf'] = int(params['shema_tf'])
        return {
            'mode_id': 'GUI-DYNAMIC',
            'Nz': float(params['Nz']),
            'Gprom': float(params['Gprom']),
            'Qtf': float(params['Qtf']),
            'shema_tf': int(params['shema_tf']),
            'W_cw': float(W_nom),
            'tw1': float(air_to_water_temp(params['t_air'])),
            'tech_state_coeff': 1.0,
            'component_health': self.collect_component_health(),
            'N_e': float(params['Nz']),
        }
    def run_dynamic_calculation(self):
        if run_dynamic_simulation is None:
            messagebox.showerror('Динамика недоступна', 'Не найден модуль dynamic_service.py')
            return
        try:
            t_end = float(self.dynamic_t_end_var.get())
            n_points = int(self.dynamic_n_points_var.get())
            if t_end <= 0 or n_points < 10:
                raise ValueError('Горизонт должен быть > 0, а число точек не меньше 10.')
            scenario_key = self._get_dynamic_selected_key()
            base_mode = self._build_dynamic_base_mode()
            self.dynamic_result = run_dynamic_simulation(
                scenario_name=scenario_key,
                t_end=t_end,
                n_points=n_points,
                base_mode=base_mode,
            )
            self.dynamic_table_df = build_dynamic_table_for_ui(self.dynamic_result) if callable(build_dynamic_table_for_ui) else self.dynamic_result.get('table')
            self.dynamic_summary = self.dynamic_result.get('summary', {})
            self.update_dynamic_tab()
            self.notebook.select(self.dynamic_tab)
        except Exception as e:
            messagebox.showerror('Ошибка динамического расчёта', str(e))
            import traceback
            traceback.print_exc()
    def update_dynamic_tab(self):
        self.update_dynamic_summary_text()
        self.update_dynamic_table()
        self.update_dynamic_plot()
    def update_dynamic_summary_text(self):
        self.dynamic_summary_text.config(state='normal')
        self.dynamic_summary_text.delete('1.0', 'end')
        if not self.dynamic_summary:
            self.dynamic_summary_text.insert('1.0', 'Нет данных динамического расчёта.')
            self.dynamic_summary_text.config(state='disabled')
            return
        summary = self.dynamic_summary
        maxima = summary.get('maxima', {})
        initial = summary.get('initial', {})
        final = summary.get('final', {})
        lines = [
            f"Сценарий: {summary.get('scenario_label', summary.get('scenario', '—'))}",
            f"Длительность: {summary.get('duration_s', 0.0):.1f} с",
            '',
            f"Начало: N={initial.get('power_mw', 0.0):.2f} МВт, G0={initial.get('g0_tph', 0.0):.2f} т/ч, Pк={initial.get('pk_kpa', 0.0):.2f} кПа",
            f"Конец:  N={final.get('power_mw', 0.0):.2f} МВт, G0={final.get('g0_tph', 0.0):.2f} т/ч, Pк={final.get('pk_kpa', 0.0):.2f} кПа, ω={final.get('omega_rads', 0.0):.3f} рад/с",
            '',
            f"Макс. мощность: {maxima.get('max_power_mw', 0.0):.2f} МВт",
            f"Макс. расход свежего пара: {maxima.get('max_g0_tph', 0.0):.2f} т/ч",
            f"Макс. давление конденсатора: {maxima.get('max_pk_kpa', 0.0):.2f} кПа",
            f"Макс. невязка баланса: {maxima.get('max_balance_error_tph', 0.0):.4f} т/ч",
        ]
        self.dynamic_summary_text.insert('1.0', '\n'.join(lines))
        self.dynamic_summary_text.config(state='disabled')
    def update_dynamic_table(self):
        for item in self.dynamic_tree.get_children():
            self.dynamic_tree.delete(item)
        if self.dynamic_table_df is None or self.dynamic_table_df.empty:
            return
        df = self.dynamic_table_df.copy()
        for _, row in df.iterrows():
            values = []
            for col in self.dynamic_table_columns:
                val = row[col] if col in df.columns else ''
                if isinstance(val, (int, float, np.floating)):
                    if col == 't':
                        values.append(f"{float(val):.1f}")
                    elif col in {'P_prom', 'P_vto', 'P_nto'}:
                        values.append(f"{float(val):.3f}")
                    elif col == 'P_k':
                        values.append(f"{float(val)*1000.0:.3f}")
                    else:
                        values.append(f"{float(val):.3f}")
                else:
                    values.append(val)
            self.dynamic_tree.insert('', 'end', values=values)
    def update_dynamic_plot(self, event=None):
        for child in self.dynamic_plot_frame.winfo_children():
            child.destroy()
        if self.dynamic_result is None or self.dynamic_result.get('table') is None:
            ttk.Label(self.dynamic_plot_frame, text='Сначала запустите динамический расчёт').pack()
            return
        df = self.dynamic_result['table']
        choice = self.dynamic_plot_choice.get()
        fig = None
        if choice == 'Мощность':
            fig = plot_dynamic_power(df)
        elif choice == 'Расходы':
            fig = plot_dynamic_flows(df)
        elif choice == 'Давления':
            fig = plot_dynamic_pressures(df)
        elif choice == 'Ротор':
            fig = plot_dynamic_rotor(df)
        elif choice == 'Баланс':
            fig = plot_dynamic_balance(df)
        if fig is None:
            ttk.Label(self.dynamic_plot_frame, text='Нет данных для выбранного графика').pack()
            return
        canvas = FigureCanvasTkAgg(fig, master=self.dynamic_plot_frame)
        canvas.draw()
        canvas.get_tk_widget().pack(fill='both', expand=True)
if __name__ == "__main__":
    root = tk.Tk()
    app = PT80App(root)
    root.mainloop()
