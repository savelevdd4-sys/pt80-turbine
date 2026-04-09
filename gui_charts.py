import matplotlib.pyplot as plt
import pandas as pd
import numpy as np


def _series_x(df: pd.DataFrame, prefer_available: bool = False):
    if prefer_available and "available_power_mw" in df.columns:
        return df["available_power_mw"], "Доступная электрическая мощность, МВт"
    if "requested_power_mw" in df.columns:
        return df["requested_power_mw"], "Запрошенная электрическая мощность, МВт"
    if "available_power_mw" in df.columns:
        return df["available_power_mw"], "Доступная электрическая мощность, МВт"
    return pd.Series(range(len(df))), "Точка расчёта"


def _style_ax(ax, title: str, xlabel: str, ylabel: str, legend: bool = False):
    ax.set_title(title)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.grid(True, alpha=0.3)
    if legend:
        ax.legend()


def plot_power_vs_steam(power_list, g0_list):
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.plot(power_list, g0_list, marker='o', linestyle='-', label='Расход свежего пара')
    _style_ax(
        ax,
        "Расход свежего пара от электрической мощности",
        "Расчётная электрическая мощность, МВт",
        "Расход свежего пара G₀, т/ч",
        legend=True,
    )
    return fig


def plot_heat_vs_power(qtf_list, power_list):
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.plot(qtf_list, power_list, marker='s', linestyle='-', label='Доступная мощность')
    _style_ax(
        ax,
        "Влияние тепловой нагрузки на электрическую мощность",
        "Тепловая нагрузка Qтф, Гкал/ч",
        "Доступная электрическая мощность, МВт",
        legend=True,
    )
    return fig


def plot_power_vs_profit(curve_data):
    df = pd.DataFrame(curve_data).sort_values(by='available_power_mw' if 'available_power_mw' in pd.DataFrame(curve_data).columns else 'requested_power_mw')
    x, xlabel = _series_x(df, prefer_available=True)
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.plot(x, df["profit_rub_per_h"], marker='o', linestyle='-', label='Прибыль')
    if not df.empty:
        best_idx = df["profit_rub_per_h"].idxmax()
        ax.scatter([df.loc[best_idx, x.name] if getattr(x, 'name', None) in df.columns else x.loc[best_idx]], [df.loc[best_idx, "profit_rub_per_h"]], marker='o', s=70, label='Оптимум')
    _style_ax(ax, "Прибыль от уровня электрической мощности", xlabel, "Прибыль, руб/ч", legend=True)
    return fig


def plot_hourly_bid(schedule_table):
    df = schedule_table.copy()
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.bar(df["hour"], df["recommended_bid_mw"], label='Рекомендуемая заявка')
    if "available_power_mw" in df.columns:
        ax.plot(df["hour"], df["available_power_mw"], marker='o', linestyle='-', label='Доступная мощность')
    _style_ax(ax, "Почасовая рекомендуемая заявка на РСВ", "Час суток", "Электрическая мощность, МВт", legend=True)
    return fig


def plot_temp_vs_pressure(temp_range, pressure_range):
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.plot(temp_range, pressure_range, marker='d', linestyle='-', label='Расчёт режима')
    _style_ax(
        ax,
        "Влияние температуры воздуха на давление в конденсаторе",
        "Температура воздуха, °C",
        "Давление в конденсаторе, кПа",
        legend=True,
    )
    return fig


def plot_csnd_pressures(p_vto, p_nto, p_k):
    labels = ['Верхний отбор', 'Нижний отбор', 'Конденсатор']
    values_kpa = [float(p_vto) * 1000.0, float(p_nto) * 1000.0, float(p_k) * 1000.0]
    fig, ax = plt.subplots(figsize=(5, 4))
    bars = ax.bar(labels, values_kpa)
    _style_ax(ax, "Давления по тракту ЦСНД", "Точка тракта", "Давление, кПа")
    for bar, val in zip(bars, values_kpa):
        ax.text(bar.get_x() + bar.get_width() / 2, val, f"{val:.1f}", ha='center', va='bottom', fontsize=9)
    return fig


def plot_hs_diagram(points):
    """points: список кортежей (h, s, label) или словарей {'h','s','label'}"""
    fig, ax = plt.subplots(figsize=(6, 5))
    normalized = []
    for point in points:
        if isinstance(point, dict):
            h = float(point.get('h', 0.0))
            s = float(point.get('s', 0.0))
            label = point.get('label', '')
        else:
            h, s, label = point
        if h > 0 and s > 0:
            normalized.append((h, s, label))

    if not normalized:
        ax.text(0.5, 0.5, 'Нет расчётных точек для h-s диаграммы', ha='center', va='center', transform=ax.transAxes)
        ax.set_title("h-s диаграмма")
        return fig

    s_line = [pt[1] for pt in normalized]
    h_line = [pt[0] for pt in normalized]
    ax.plot(s_line, h_line, marker='o', linestyle='-', label='Линия процесса')
    for h, s, label in normalized:
        ax.scatter(s, h)
        ax.annotate(label, (s, h), textcoords='offset points', xytext=(5, 5))
    _style_ax(ax, "h-s диаграмма режима", "Энтропия s, кДж/(кг·К)", "Энтальпия h, кДж/кг", legend=True)
    return fig


def plot_steam_balance(balance_dict):
    labels = ['Регенерация', 'Производство', 'Теплофикация верх', 'Теплофикация низ', 'Конденсатор']
    values = [
        balance_dict['regeneration_extractions_tph'],
        balance_dict['production_extraction_tph'],
        balance_dict['heating_upper_tph'],
        balance_dict['heating_lower_tph'],
        balance_dict['to_condenser_tph']
    ]
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.pie(values, labels=labels, autopct='%1.1f%%')
    ax.set_title("Баланс потоков пара по направлениям")
    return fig


def plot_regeneration_structure(regen_data):
    if isinstance(regen_data, dict):
        regen_rows = regen_data.get('rows', [])
        regen_summary = regen_data.get('summary', {})
    else:
        regen_rows = regen_data
        regen_summary = {}

    groups = {'ПВД': 0.0, 'ПНД': 0.0, 'ДА': 0.0}
    for row in regen_rows:
        try:
            grp = row.get('group')
            flow = float(row.get('flow_tph', 0.0))
        except (TypeError, ValueError, AttributeError):
            continue
        if grp in groups:
            groups[grp] += max(0.0, flow)

    labels = [grp for grp, val in groups.items() if val > 0]
    values = [groups[grp] for grp in labels]
    fig, ax = plt.subplots(figsize=(6, 4))
    bars = ax.bar(labels, values)
    _style_ax(ax, "Распределение расходов пара по группам регенерации", "Группа регенерации", "Расход пара, т/ч")
    for bar, val in zip(bars, values):
        ax.text(bar.get_x() + bar.get_width() / 2, val, f"{val:.1f}", ha='center', va='bottom', fontsize=9)
    if regen_summary:
        total = float(regen_summary.get('total_regen_flow_tph', 0.0))
        t_ok = float(regen_summary.get('t_ok_c', 0.0))
        t_pv = float(regen_summary.get('t_pv_c', 0.0))
        ax.text(0.02, 0.98, f"ΣGрег = {total:.1f} т/ч\nt_ok = {t_ok:.1f} °C\nt_пв = {t_pv:.1f} °C",
                transform=ax.transAxes, va='top', ha='left',
                bbox=dict(boxstyle='round', facecolor='white', alpha=0.8))
    return fig


def plot_cost_margin(curve_data):
    df = pd.DataFrame(curve_data).sort_values(by='available_power_mw' if 'available_power_mw' in pd.DataFrame(curve_data).columns else 'requested_power_mw')
    x, xlabel = _series_x(df, prefer_available=True)
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.plot(x, df["fuel_cost_rub_per_mwh"], label='Топливная себестоимость', marker='.')
    ax.plot(x, df["margin_rub_per_mwh"], label='Маржа', marker='.')
    ax.axhline(y=0, color='gray', linestyle='--')
    _style_ax(ax, "Себестоимость и маржа от уровня мощности", xlabel, "руб/МВт·ч", legend=True)
    return fig

def _plot_no_data(title: str, subtitle: str = "Нет данных"):
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.text(0.5, 0.58, title, ha='center', va='center', fontsize=12, transform=ax.transAxes)
    ax.text(0.5, 0.42, subtitle, ha='center', va='center', fontsize=10, color='gray', transform=ax.transAxes)
    ax.set_axis_off()
    return fig


def _time_series(df: pd.DataFrame):
    if df is None or len(df) == 0:
        return None, None
    if "time_s" in df.columns:
        return df["time_s"], "Время, с"
    if "t" in df.columns:
        return df["t"], "Время, с"
    return pd.Series(range(len(df))), "Шаг"


def _pick(df: pd.DataFrame, candidates):
    for c in candidates:
        if c in df.columns:
            return c
    return None


def plot_dynamic_power(df: pd.DataFrame):
    if df is None or len(df) == 0:
        return _plot_no_data("Динамика мощности")

    t, xlabel = _time_series(df)
    power_col = _pick(df, ["N_el_net", "N_el_actual", "N_el_gross", "power_mw", "Nz_set", "Nz"])
    if power_col is None:
        return _plot_no_data("Динамика мощности", "Нет столбца мощности")

    fig, ax = plt.subplots(figsize=(7, 4))
    ax.plot(t, df[power_col], label=power_col)

    if "Nz_set" in df.columns and power_col != "Nz_set":
        ax.plot(t, df["Nz_set"], linestyle="--", label="Nz_set")
    elif "Nz" in df.columns and power_col != "Nz":
        ax.plot(t, df["Nz"], linestyle="--", label="Nz")

    _style_ax(ax, "Динамика мощности", xlabel, "Мощность, МВт", legend=True)
    return fig


def plot_dynamic_flows(df: pd.DataFrame):
    if df is None or len(df) == 0:
        return _plot_no_data("Динамика расходов")

    t, xlabel = _time_series(df)
    candidates = [
        ("G0", "G0"),
        ("G_cond", "Gк"),
        ("G_vto", "G_ВТО"),
        ("G_nto", "G_НТО"),
        ("G_to_csnd", "G_вх_ЦСНД"),
        ("Gprom", "Gпром"),
    ]
    present = [(c, l) for c, l in candidates if c in df.columns]
    if not present:
        return _plot_no_data("Динамика расходов", "Нет расходных столбцов")

    fig, ax = plt.subplots(figsize=(7, 4))
    for c, l in present:
        ax.plot(t, df[c], label=l)

    _style_ax(ax, "Динамика расходов", xlabel, "Расход, т/ч", legend=True)
    return fig


def plot_dynamic_pressures(df: pd.DataFrame):
    if df is None or len(df) == 0:
        return _plot_no_data("Динамика давлений")

    t, xlabel = _time_series(df)
    candidates = [
        ("P_prom", "Pпром"),
        ("P_vto", "Pвто"),
        ("P_nto", "Pнто"),
        ("P_k", "Pк"),
        ("P4", "P4"),
        ("P5", "P5"),
        ("P6", "P6"),
        ("P7", "P7"),
    ]
    present = [(c, l) for c, l in candidates if c in df.columns]
    if not present:
        return _plot_no_data("Динамика давлений", "Нет столбцов давления")

    fig, ax = plt.subplots(figsize=(7, 4))
    for c, l in present:
        y = df[c] * 1000.0 if c == "P_k" else df[c]
        ax.plot(t, y, label=l)

    _style_ax(ax, "Динамика давлений", xlabel, "Давление", legend=True)
    return fig


def plot_dynamic_rotor(df: pd.DataFrame):
    if df is None or len(df) == 0:
        return _plot_no_data("Динамика ротора")

    t, xlabel = _time_series(df)
    rotor_col = _pick(df, ["omega", "n_rotor", "speed_rpm"])
    if rotor_col is None:
        return _plot_no_data("Динамика ротора", "Нет столбца скорости ротора")

    fig, ax = plt.subplots(figsize=(7, 4))
    ax.plot(t, df[rotor_col], label=rotor_col)

    _style_ax(ax, "Динамика ротора", xlabel, "Скорость / ω", legend=True)
    return fig


def plot_dynamic_balance(df: pd.DataFrame):
    if df is None or len(df) == 0:
        return _plot_no_data("Баланс и запас до ЕПД")

    t, xlabel = _time_series(df)
    candidates = [
        ("delta_balance", "Невязка баланса"),
        ("t_regime_n_margin_mw", "Запас по N"),
        ("epd_margin_tph", "Запас до ЕПД"),
    ]
    present = [(c, l) for c, l in candidates if c in df.columns]
    if not present:
        return _plot_no_data("Баланс и запас до ЕПД", "Нет нужных столбцов")

    fig, ax = plt.subplots(figsize=(7, 4))
    for c, l in present:
        ax.plot(t, df[c], label=l)

    _style_ax(ax, "Баланс и запас до ЕПД", xlabel, "Значение", legend=True)
    return fig