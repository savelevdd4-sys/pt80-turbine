from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Callable

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.integrate import solve_ivp

from dynamic_model import build_initial_state, rhs, algebraic_outputs, unpack_state
from dynamic_scenarios import DEFAULT_BASE_MODE, get_schedule, list_scenarios, make_base_mode

DYN_PARAMS = {
    "T_G0": 2.0,
    "T_P1": 0.8,
    "T_P2": 0.8,
    "T_P3": 0.8,
    "T_P_prom": 1.0,
    "T_P4": 1.2,
    "T_P5": 1.2,
    "T_P6": 1.2,
    "T_P7": 1.2,
    "T_P_vto": 2.0,
    "T_P_nto": 2.0,
    "T_P_k": 8.0,
    "T_G1": 6.0,
    "T_G2": 6.0,
    "T_G3": 6.0,
    "T_G4": 6.0,
    "T_G5": 6.0,
    "T_G6": 6.0,
    "T_G7": 6.0,
    "T_G_steam_d": 5.0,
    "T_G_vto": 5.0,
    "T_G_nto": 5.0,
    "T_G_cond": 3.0,
    "omega_nom": 2.0 * np.pi * 50.0,
    "J_rotor": 25.0,
    "D_omega": 2.0,
    "k_balance": 0.5,
    "x_start": 0.98,
}


def run_simulation(
    t_end: float = 600.0,
    n_points: int = 1201,
    base_mode: dict[str, Any] | None = None,
    schedule: Callable[[float], dict[str, Any]] | None = None,
    scenario_name: str = "combined_demo",
    params: dict[str, Any] | None = None,
    method: str = "RK45",
    max_step: float = 1.0,
):
    dyn_params = dict(DYN_PARAMS)
    if params:
        dyn_params.update(params)

    base = make_base_mode(**(base_mode or DEFAULT_BASE_MODE))
    schedule_fn = schedule or get_schedule(scenario_name, base)

    x0 = build_initial_state(base, dyn_params)
    t_span = (0.0, float(t_end))
    t_eval = np.linspace(t_span[0], t_span[1], int(n_points))

    def rhs_for_solver(t: float, x: np.ndarray) -> np.ndarray:
        u = schedule_fn(float(t))
        return rhs(t, x, u, dyn_params)

    sol = solve_ivp(
        rhs_for_solver,
        t_span=t_span,
        y0=x0,
        t_eval=t_eval,
        method=method,
        rtol=1e-5,
        atol=1e-7,
        max_step=max_step,
    )
    if not sol.success:
        raise RuntimeError(f"Интегрирование неуспешно: {sol.message}")
    return sol, schedule_fn, dyn_params


def build_results_dataframe(sol, schedule, params: dict[str, Any]) -> pd.DataFrame:
    rows = []
    for i, t in enumerate(sol.t):
        x = sol.y[:, i]
        s = unpack_state(x)
        u = schedule(float(t))
        alg = algebraic_outputs(x, u, params)
        row = {
            "t": float(t),
            **s,
            "Nz_set": float(u["Nz"]),
            "Ne_load": float(u.get("N_e", u["Nz"])),
            "Gprom_set": float(u["Gprom"]),
            "Qtf_set": float(u["Qtf"]),
            "tw1": float(u["tw1"]),
            "W_cw": float(u["W_cw"]),
            "N_cvd": float(alg["N_cvd"]),
            "N_csnd": float(alg["N_csnd"]),
            "N_el_gross": float(alg["N_el_gross"]),
            "N_el_actual": float(alg["N_el_actual"]),
            "dN_cond": float(alg["dN_cond"]),
            "dN_tf": float(alg["dN_tf"]),
            "delta_balance": float(alg["delta_balance"]),
            "P1_ref": float(alg["refs"]["P1_ref"]),
            "P2_ref": float(alg["refs"]["P2_ref"]),
            "P3_ref": float(alg["refs"]["P3_ref"]),
            "P_prom_ref": float(alg["refs"]["P_prom_ref"]),
            "P4_ref": float(alg["refs"]["P4_ref"]),
            "P5_ref": float(alg["refs"]["P5_ref"]),
            "P6_ref": float(alg["refs"]["P6_ref"]),
            "P7_ref": float(alg["refs"]["P7_ref"]),
            "P_vto_ref": float(alg["refs"]["P_vto_ref"]),
            "P_nto_ref": float(alg["refs"]["P_nto_ref"]),
            "P_k_ref": float(alg["refs"]["P_k_ref"]),
            "G0_ref": float(alg["refs"]["G0_ref"]),
            "G_cond_ref": float(alg["refs"]["G_cond_ref"]),
            "h4": float(alg["csnd_enthalpies"]["h4"]),
            "h5": float(alg["csnd_enthalpies"]["h5"]),
            "h6": float(alg["csnd_enthalpies"]["h6"]),
            "h7": float(alg["csnd_enthalpies"]["h7"]),
            "h_vto": float(alg["csnd_enthalpies"]["h_vto"]),
            "h_nto": float(alg["csnd_enthalpies"]["h_nto"]),
            "h_k": float(alg["csnd_enthalpies"]["h_k"]),
            "Q_k": float(alg["cond_results"]["Q_k"]),
            "tsat_k": float(alg["cond_results"]["tsat"]),
            "tw2": float(alg["cond_results"]["tw2"]),
        }
        rows.append(row)
    return pd.DataFrame(rows)


def save_results(df: pd.DataFrame, path: str | Path) -> Path:
    path = Path(path)
    df.to_csv(path, index=False, encoding="utf-8-sig")
    return path


def plot_results(df: pd.DataFrame) -> None:
    fig1 = plt.figure(figsize=(10, 5))
    plt.plot(df["t"], df["N_el_actual"], label="N_el_actual")
    plt.plot(df["t"], df["Ne_load"], label="N_e load")
    plt.plot(df["t"], df["Nz_set"], label="Nz set")
    plt.xlabel("t, c")
    plt.ylabel("МВт")
    plt.title("Электрическая мощность")
    plt.grid(True)
    plt.legend()

    fig2 = plt.figure(figsize=(10, 5))
    plt.plot(df["t"], df["G0"], label="G0")
    plt.plot(df["t"], df["G_cond"], label="G_cond")
    plt.plot(df["t"], df["G_vto"], label="G_vto")
    plt.plot(df["t"], df["G_nto"], label="G_nto")
    plt.xlabel("t, c")
    plt.ylabel("т/ч")
    plt.title("Расходы")
    plt.grid(True)
    plt.legend()

    fig3 = plt.figure(figsize=(10, 5))
    plt.plot(df["t"], df["P_prom"] * 1000.0, label="P_prom")
    plt.plot(df["t"], df["P_vto"] * 1000.0, label="P_vto")
    plt.plot(df["t"], df["P_nto"] * 1000.0, label="P_nto")
    plt.plot(df["t"], df["P_k"] * 1000.0, label="P_k")
    plt.xlabel("t, c")
    plt.ylabel("кПа")
    plt.title("Ключевые давления")
    plt.grid(True)
    plt.legend()

    fig4 = plt.figure(figsize=(10, 5))
    plt.plot(df["t"], df["omega"], label="omega")
    plt.xlabel("t, c")
    plt.ylabel("рад/с")
    plt.title("Скорость ротора")
    plt.grid(True)
    plt.legend()

    fig5 = plt.figure(figsize=(10, 5))
    plt.plot(df["t"], df["delta_balance"], label="delta_balance")
    plt.xlabel("t, c")
    plt.ylabel("т/ч")
    plt.title("Невязка материального баланса")
    plt.grid(True)
    plt.legend()

    plt.show()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Динамическая симуляция ПТ-80/100-130/13")
    parser.add_argument("--scenario", default="combined_demo", choices=list_scenarios(), help="Имя сценария")
    parser.add_argument("--t-end", type=float, default=600.0, help="Горизонт моделирования, с")
    parser.add_argument("--n-points", type=int, default=1201, help="Число точек результата")
    parser.add_argument("--out", type=str, default="dynamic_results.csv", help="Путь к CSV")
    parser.add_argument("--no-plot", action="store_true", help="Не строить графики")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    sol, schedule, dyn_params = run_simulation(
        t_end=args.t_end,
        n_points=args.n_points,
        scenario_name=args.scenario,
    )
    df = build_results_dataframe(sol, schedule, dyn_params)
    out_path = save_results(df, args.out)
    print(df[[
        "t", "N_el_actual", "Ne_load", "Nz_set", "G0", "G_cond", "P_prom", "P_vto", "P_nto", "P_k", "delta_balance"
    ]].tail(10).to_string(index=False))
    print(f"\nРезультаты сохранены в: {out_path.resolve()}")
    if not args.no_plot:
        plot_results(df)


if __name__ == "__main__":
    main()
