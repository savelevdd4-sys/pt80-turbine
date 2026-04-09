import contextlib
import io

def run_mode_calculation(mode_data: dict) -> dict:
    from main import calculate_mode
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        results = calculate_mode(mode_data)
    return {"results": results, "log": buf.getvalue()}
