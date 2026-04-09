from regime_maps import validate_t_mode, validate_p_mode


def evaluate_limits(power_mw: float, steam_flow_tph: float, condenser_kpa: float, fresh_steam_temp_c: float, tech_limit_mw: float,
                    qtf_gcal_h: float = 0.0, qprom_gcal_h: float = 0.0, gcsd_tph: float | None = None) -> dict:
    available = float(power_mw)
    violations = []

    if tech_limit_mw > 0 and available > tech_limit_mw:
        available = tech_limit_mw
        violations.append("технический предел мощности")

    if steam_flow_tph > 470.0:
        limited = max(0.0, available - (steam_flow_tph - 470.0) * 0.18)
        if limited < available:
            available = limited
            violations.append("ограничение по расходу свежего пара")

    if condenser_kpa > 12.0:
        limited = max(0.0, available - (condenser_kpa - 12.0) * 0.7)
        if limited < available:
            available = limited
            violations.append("ограничение по вакууму")

    if fresh_steam_temp_c < 535.0:
        limited = max(0.0, available - (535.0 - fresh_steam_temp_c) * 0.12)
        if limited < available:
            available = limited
            violations.append("ограничение по температуре свежего пара")

    t_check = validate_t_mode(available, qtf_gcal_h, g0_tph=steam_flow_tph, gcsd_tph=gcsd_tph)
    if t_check['is_applicable'] and not t_check['is_valid']:
        available = min(available, t_check['nmax_mw'])
        violations.extend(t_check['violations'])

    p_check = validate_p_mode(available, qprom_gcal_h)
    if p_check['is_applicable'] and not p_check['is_valid']:
        available = min(available, p_check['nreal_max_mw'])
        violations.extend(p_check['violations'])

    return {
        "available_power_mw": round(available, 3),
        "has_limit": bool(violations),
        "violations": violations,
        "t_regime": t_check,
        "pt_regime": p_check,
    }
