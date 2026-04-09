import pandas as pd
import plotly.graph_objects as go

def build_profit_curve(curve):
    df = pd.DataFrame(curve)
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df["requested_power_mw"], y=df["profit_rub_per_h"], mode="lines", name="Прибыль"))
    fig.update_layout(title="Оптимизация нагрузки по прибыли (по реальному calculate_mode)", xaxis_title="Запрошенная мощность, МВт", yaxis_title="Прибыль, руб/ч")
    return fig

def build_hourly_bid_chart(df):
    fig = go.Figure()
    fig.add_trace(go.Bar(x=df["hour"], y=df["recommended_bid_mw"], name="Заявка РСВ, МВт"))
    fig.update_layout(title="Почасовая рекомендуемая заявка на рынок «сутки вперёд»", xaxis_title="Час суток", yaxis_title="МВт")
    return fig
