from __future__ import annotations

from typing import Dict, Any


def _f(value: Any, digits: int = 2) -> str:
    try:
        return f"{float(value):.{digits}f}"
    except Exception:
        return "—"


def build_human_formula_report(results: Dict[str, Any], inputs: Dict[str, Any]) -> str:
    qtf_kw = float(results.get('Qtf', 0.0)) * 1163.0
    shema = int(results.get('shema_tf', inputs.get('shema_tf', 1)))
    lines = []
    add = lines.append
    add("РАСЧЁТ СХЕМЫ ПТ-80/100-130/13 В ИНЖЕНЕРНОЙ ЗАПИСИ")
    add("=" * 78)
    add("")
    add("1. Исходные условия")
    add("-" * 78)
    add(f"Nz = {_f(results.get('Nz', inputs.get('Nz', 0.0)), 2)} МВт")
    add(f"Gпром = {_f(results.get('Gprom', inputs.get('Gprom', 0.0)), 2)} т/ч")
    add(f"Qтф = {_f(results.get('Qtf', inputs.get('Qtf', 0.0)), 2)} Гкал/ч")
    add(f"Схема теплофикации = {'одноступенчатая' if shema == 1 else 'двухступенчатая'}")
    add(f"tвх,ПСГ = {_f(inputs.get('t_water_in', 50.0), 1)} °C")
    if float(inputs.get('G_water_psg', 0.0) or 0.0) > 0:
        add(f"Gсв = {_f(inputs.get('G_water_psg'), 1)} т/ч")
    add("")
    add("2. Баланс свежего пара")
    add("-" * 78)
    add("G0 = G1 + G2 + G3 + G4 + G5 + G6 + G7 + Gд + Gпром + Gвто + Gнто + Gк")
    add(
        f"G0 = {_f(results.get('G1'))} + {_f(results.get('G2'))} + {_f(results.get('G3'))} + "
        f"{_f(results.get('G4'))} + {_f(results.get('G5'))} + {_f(results.get('G6'))} + "
        f"{_f(results.get('G7'))} + {_f(results.get('G_steam_d'))} + {_f(results.get('Gprom'))} + "
        f"{_f(results.get('G_vto'))} + {_f(results.get('G_nto'))} + {_f(results.get('G_cond'))}"
    )
    add(f"G0 = {_f(results.get('G0'))} т/ч")
    add("")
    add("3. Электрическая мощность")
    add("-" * 78)
    add("Nэл,брутто = (Nцвд + Nцснд) · ηмех · ηген · kтехсост")
    add(
        f"Nэл,брутто = ({_f(results.get('N_cvd'))} + {_f(results.get('N_csnd'))}) -> {_f(results.get('N_el_gross'))} МВт"
    )
    add("Nэл,факт = Nэл,брутто - ΔNвакуум")
    add(f"Nэл,факт = {_f(results.get('N_el_gross'))} - {_f(results.get('dN_cond'))} = {_f(results.get('N_el_actual'))} МВт")
    add("Nэл,нетто = Nэл,факт - Nсн")
    add(f"Nэл,нетто = {_f(results.get('N_el_actual'))} - {_f(results.get('N_aux'))} = {_f(results.get('N_el_net'))} МВт")
    add("")
    add("4. Теплофикация и ПСГ")
    add("-" * 78)
    add(f"Qтф,кВт = {_f(results.get('Qtf'), 2)} · 1163 = {_f(qtf_kw, 2)} кВт")
    if shema == 1:
        add("Одноступенчатая схема: вся нагрузка идёт на нижний отопительный отбор и один ПСГ.")
        if isinstance(results.get('psv1'), dict):
            psv1 = results['psv1']
            add(
                f"ПСГ: Gпар = {_f(psv1.get('G_steam_tph'))} т/ч, "
                f"Pпар = {_f(psv1.get('P_steam_mpa'), 3)} МПа, "
                f"tвых,св = {_f(psv1.get('t_water_out_c'), 1)} °C"
            )
    else:
        add("Двухступенчатая схема: нижняя ступень предварительно нагревает воду, верхняя завершает нагрев.")
        nto = results.get('psv_nto', {}) if isinstance(results.get('psv_nto'), dict) else {}
        vto = results.get('psv_vto', {}) if isinstance(results.get('psv_vto'), dict) else {}
        add(
            f"ПСГ-1/НТО: Gпар = {_f(nto.get('G_steam_tph'))} т/ч, "
            f"Pпар = {_f(nto.get('P_steam_mpa'), 3)} МПа, "
            f"tвых = {_f(nto.get('t_water_out_c'), 1)} °C"
        )
        add(
            f"ПСГ-2/ВТО: Gпар = {_f(vto.get('G_steam_tph'))} т/ч, "
            f"Pпар = {_f(vto.get('P_steam_mpa'), 3)} МПа, "
            f"tвых = {_f(vto.get('t_water_out_c'), 1)} °C"
        )
    add("")
    add("5. Экономичность")
    add("-" * 78)
    add(f"Q0 = {_f(results.get('Q0'), 2)} Гкал/ч")
    add(f"qт,брутто = {_f(results.get('q_t'), 1)} ккал/кВт·ч")
    add(f"qт,нетто = {_f(results.get('q_t_net'), 1)} ккал/кВт·ч")
    add(f"ηбрутто = {_f(results.get('eta_brut'), 2)} %")
    add(f"ηнетто = {_f(results.get('eta_net'), 2)} %")
    add("")
    add("6. Итог")
    add("-" * 78)
    add(
        f"Режим сошёлся за {int(results.get('iterations', 0))} итерац.; "
        f"невязка баланса = {_f(results.get('delta_balance'), 3)} т/ч; "
        f"давление в конденсаторе = {_f(float(results.get('P_k', 0.0)) * 1000.0, 2)} кПа."
    )
    return "\n".join(lines)
