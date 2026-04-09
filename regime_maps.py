import math
from typing import Iterable, Sequence

from steam_properties import h_steam_sat, h_water_temp


def _sorted_points(points: Iterable[tuple[float, float]]) -> list[tuple[float, float]]:
    pts = sorted((float(x), float(y)) for x, y in points)
    if len(pts) < 2:
        raise ValueError('Need at least two points for interpolation')
    return pts


def piecewise_linear(x: float, points: Sequence[tuple[float, float]]) -> float:
    pts = _sorted_points(points)
    x = float(x)
    if x <= pts[0][0]:
        (x0, y0), (x1, y1) = pts[0], pts[1]
        if abs(x1 - x0) < 1e-12:
            return y0
        return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    if x >= pts[-1][0]:
        (x0, y0), (x1, y1) = pts[-2], pts[-1]
        if abs(x1 - x0) < 1e-12:
            return y1
        return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    for (x0, y0), (x1, y1) in zip(pts[:-1], pts[1:]):
        if x0 <= x <= x1:
            if abs(x1 - x0) < 1e-12:
                return y0
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return pts[-1][1]



# --- Т-режим: табличная карта по узловым точкам ---
T_MODE_SLICE_POINTS = {
    0.0: [(27.0, 120.0, 100.0), (33.0, 140.0, 120.0), (40.0, 162.0, 140.0), (47.0, 190.0, 160.0), (55.0, 218.0, 180.0), (65.0, 252.0, 200.0), (71.0, 278.0, 220.0)],
    30.0: [(30.0, 160.0, 80.0), (37.0, 180.0, 100.0), (43.0, 202.0, 120.0), (52.0, 237.0, 140.0), (58.0, 259.0, 160.0), (65.0, 280.0, 180.0), (73.0, 302.0, 200.0), (78.0, 329.0, 220.0)],
    60.0: [(40.0, 221.0, 80.0), (48.0, 250.0, 100.0), (55.0, 278.0, 120.0), (63.0, 300.0, 140.0), (69.0, 322.0, 160.0), (75.0, 342.0, 180.0), (83.0, 380.0, 200.0), (90.0, 401.0, 220.0)],
    90.0: [(53.0, 298.0, 80.0), (59.0, 320.0, 100.0), (66.0, 341.0, 120.0), (73.0, 372.0, 140.0), (79.0, 398.0, 160.0), (87.0, 420.0, 180.0), (93.0, 445.0, 200.0), (97.0, 470.0, 220.0)],
    120.0: [(63.0, 363.0, 80.0), (69.0, 380.0, 100.0), (77.0, 418.0, 120.0), (83.0, 440.0, 140.0), (90.0, 470.0, 162.0)],
    150.0: [(73.0, 440.0, 80.0), (80.0, 470.0, 110.0)],
}

T_EPD_POINTS = {
    0.0: (73.0, 82.0),
    30.0: (80.0, 91.0),
    60.0: (91.0, 100.0),
    90.0: (98.0, 100.0),
}

K_MODE_NMIN_MW = 17.0
K_MODE_NMAX_MW = 74.0


def _interp_on_slice(points: Sequence[tuple[float, float, float]], n: float, idx: int) -> float:
    pts = [(p[0], p[idx]) for p in points]
    return float(piecewise_linear(float(n), pts))


def _interp_t_q(q: float, pairs: Sequence[tuple[float, float]]) -> float:
    return float(piecewise_linear(float(q), pairs))


def t_mode_nmin(qtf_gcal_h: float) -> float:
    pts = [(q, values[0][0]) for q, values in sorted(T_MODE_SLICE_POINTS.items())]
    return _interp_t_q(qtf_gcal_h, pts)


def t_mode_nmax(qtf_gcal_h: float) -> float:
    pts = [(q, values[-1][0]) for q, values in sorted(T_MODE_SLICE_POINTS.items())]
    return _interp_t_q(qtf_gcal_h, pts)


def t_mode_epd_bounds(qtf_gcal_h: float) -> tuple[float, float] | None:
    q = float(qtf_gcal_h)
    qs = sorted(T_EPD_POINTS)
    if q < qs[0] or q > qs[-1]:
        return None
    lo = piecewise_linear(q, [(qq, rng[0]) for qq, rng in sorted(T_EPD_POINTS.items())])
    hi = piecewise_linear(q, [(qq, rng[1]) for qq, rng in sorted(T_EPD_POINTS.items())])
    return float(lo), float(hi)


def t_mode_reference(qtf_gcal_h: float, n_real_mw: float) -> tuple[float | None, float | None]:
    q = float(qtf_gcal_h)
    n = float(n_real_mw)
    qs = sorted(T_MODE_SLICE_POINTS)
    if q <= qs[0]:
        q0 = q1 = qs[0]
    elif q >= qs[-1]:
        q0 = q1 = qs[-1]
    else:
        for a, b in zip(qs[:-1], qs[1:]):
            if a <= q <= b:
                q0, q1 = a, b
                break

    def per_slice(qslice: float):
        pts = T_MODE_SLICE_POINTS[qslice]
        if not (pts[0][0] <= n <= pts[-1][0]):
            return None, None
        return _interp_on_slice(pts, n, 1), _interp_on_slice(pts, n, 2)

    g0_0, gcsd_0 = per_slice(q0)
    if q0 == q1:
        return g0_0, gcsd_0

    g0_1, gcsd_1 = per_slice(q1)
    if g0_0 is None or g0_1 is None or gcsd_0 is None or gcsd_1 is None:
        return None, None

    frac = 0.0 if abs(q1 - q0) < 1e-12 else (q - q0) / (q1 - q0)
    return (
        float(g0_0 + (g0_1 - g0_0) * frac),
        float(gcsd_0 + (gcsd_1 - gcsd_0) * frac),
    )


def validate_t_mode(n_real_mw: float, qtf_gcal_h: float, g0_tph: float | None = None, gcsd_tph: float | None = None, tol_mw: float = 0.25, tol_tph: float = 2.0) -> dict:
    qtf = float(qtf_gcal_h)
    n = float(n_real_mw)

    out = {
        'is_applicable': qtf >= 0.0,
        'is_valid': True,
        'nmin_mw': round(t_mode_nmin(qtf), 3),
        'nmax_mw': round(t_mode_nmax(qtf), 3),
        'g0_boundary_tph': None,
        'gcsd_limit_tph': None,
        'violations': [],
        'warnings': [],
        'epd_bounds_mw': None,
    }

    # Для чистого К-режима отдельный диапазон.
    if qtf <= 0.0:
        out['nmin_mw'] = K_MODE_NMIN_MW
        out['nmax_mw'] = K_MODE_NMAX_MW
        if n < K_MODE_NMIN_MW - tol_mw or n > K_MODE_NMAX_MW + tol_mw:
            out['is_valid'] = False
            out['violations'].append(f"недопустимый К-режим: N={n:.2f} МВт вне [{K_MODE_NMIN_MW:.2f}; {K_MODE_NMAX_MW:.2f}]")
        return out

    nmin = t_mode_nmin(qtf)
    nmax = t_mode_nmax(qtf)
    if n < nmin - tol_mw or n > nmax + tol_mw:
        out['is_valid'] = False
        out['violations'].append(f"несуществующий Т-режим: N={n:.2f} МВт вне [{nmin:.2f}; {nmax:.2f}] при Qтф={qtf:.1f}")

    epd = t_mode_epd_bounds(qtf)
    out['epd_bounds_mw'] = None if epd is None else (round(epd[0], 3), round(epd[1], 3))
    if epd is not None and epd[0] - tol_mw <= n <= epd[1] + tol_mw:
        out['is_valid'] = False
        out['violations'].append(f"попадание в область ЕПД: N={n:.2f} МВт в [{epd[0]:.2f}; {epd[1]:.2f}] при Qтф={qtf:.1f}")

    g0_ref, gcsd_ref = t_mode_reference(qtf, n)
    if g0_ref is not None:
        out['g0_boundary_tph'] = round(g0_ref, 3)
        if g0_tph is not None and abs(float(g0_tph) - g0_ref) > max(tol_tph, 25.0):
            out['warnings'].append(f"расход на ЦВД отклоняется от табличного: G0={float(g0_tph):.1f} т/ч, ориентир={g0_ref:.1f} т/ч")
    if gcsd_ref is not None:
        out['gcsd_limit_tph'] = round(gcsd_ref, 3)
        if gcsd_tph is not None and abs(float(gcsd_tph) - gcsd_ref) > max(tol_tph, 20.0):
            out['warnings'].append(f"расход на ЦСНД отклоняется от табличного: Gцсд={float(gcsd_tph):.1f} т/ч, ориентир={gcsd_ref:.1f} т/ч")

# --- ПТ-режим: карта по мнимой мощности ---
P_IMAG_MIN_POINTS = [
    (0.0, 40.0),
    (30.0, 40.0),
    (60.0, 37.0),
    (90.0, 50.0),
    (120.0, 60.0),
    (150.0, 72.0),
]

P_IMAG_MAX_POINTS = [
    (0.0, 80.0),
    (30.0, 92.0),
    (60.0, 97.0),
    (90.0, 100.0),
    (120.0, 91.0),
    (150.0, 80.0),
]

IMAG_TO_REAL_OFFSET_MW = 7.0


def p_mode_nimag_min(qprom_gcal_h: float) -> float:
    return float(piecewise_linear(qprom_gcal_h, P_IMAG_MIN_POINTS))


def p_mode_nimag_max(qprom_gcal_h: float) -> float:
    return float(piecewise_linear(qprom_gcal_h, P_IMAG_MAX_POINTS))


def p_mode_nreal_min(qprom_gcal_h: float) -> float:
    return p_mode_nimag_min(qprom_gcal_h) - IMAG_TO_REAL_OFFSET_MW


def p_mode_nreal_max(qprom_gcal_h: float) -> float:
    return p_mode_nimag_max(qprom_gcal_h) - IMAG_TO_REAL_OFFSET_MW


def real_to_imag_power(n_real_mw: float) -> float:
    return float(n_real_mw) + IMAG_TO_REAL_OFFSET_MW


def imag_to_real_power(n_imag_mw: float) -> float:
    return float(n_imag_mw) - IMAG_TO_REAL_OFFSET_MW


def estimate_qprom_from_gprom(gprom_tph: float, p_prom_mpa: float = 1.28, t_return_c: float = 100.0) -> float:
    # Оценка тепловой нагрузки производственного отбора по тепловому содержанию отбора.
    if gprom_tph <= 0:
        return 0.0
    h_ext = h_steam_sat(max(0.8, p_prom_mpa))
    h_ret = h_water_temp(t_return_c)
    dh = max(0.0, h_ext - h_ret)
    q_kw = float(gprom_tph) * 1000.0 / 3600.0 * dh
    return q_kw / 1163.0


def validate_p_mode(n_real_mw: float, qprom_gcal_h: float, tol_mw: float = 0.25) -> dict:
    qp = float(qprom_gcal_h)
    n_real = float(n_real_mw)
    n_imag = real_to_imag_power(n_real)
    nimag_min = p_mode_nimag_min(qp)
    nimag_max = p_mode_nimag_max(qp)
    nreal_min = nimag_min - IMAG_TO_REAL_OFFSET_MW
    nreal_max = nimag_max - IMAG_TO_REAL_OFFSET_MW
    out = {
        'is_applicable': qp > 0.0,
        'is_valid': True,
        'n_imag_mw': round(n_imag, 3),
        'nimag_min_mw': round(nimag_min, 3),
        'nimag_max_mw': round(nimag_max, 3),
        'nreal_min_mw': round(nreal_min, 3),
        'nreal_max_mw': round(nreal_max, 3),
        'violations': [],
        'warnings': [],
    }
    if qp <= 0.0:
        return out
    if n_imag < nimag_min - tol_mw:
        out['is_valid'] = False
        out['violations'].append(f"реальная мощность ниже нижней границы ПТ-режима: Nreal={n_real:.2f} МВт < {nreal_min:.2f} МВт при Qпр={qp:.1f} Гкал/ч")
    if n_imag > nimag_max + tol_mw:
        out['is_valid'] = False
        out['violations'].append(f"реальная мощность выше верхней границы ПТ-режима: Nreal={n_real:.2f} МВт > {nreal_max:.2f} МВт при Qпр={qp:.1f} Гкал/ч")
    return out
