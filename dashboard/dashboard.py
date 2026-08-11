"""
Day 13 AI Observability Dashboard
Nguồn dữ liệu: data/logs.jsonl
Chạy: streamlit run dashboard/dashboard.py
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import streamlit as st
import plotly.graph_objects as go
import plotly.express as px

# ── Config ────────────────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parent.parent
LOGS_PATH = REPO_ROOT / "data" / "logs.jsonl"

SLO_LATENCY_P95 = 3000       # ms
SLO_ERROR_RATE  = 2.0        # %
SLO_QUALITY     = 0.75       # score 0-1
SLO_COST_TOTAL  = 2.5        # USD
SLO_TOKENS_TOTAL = 50_000    # tokens

TIME_RANGE_MINUTES = 60
REFRESH_SECONDS    = 30

PANEL_BG   = "#0e1117"
ACCENT     = "#00c8ff"
WARN_COLOR = "#ff6b35"
OK_COLOR   = "#00e676"
GRID_COLOR = "#1e2a3a"

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Day 13 AI Observability",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

html, body, [class*="css"] { font-family: 'Inter', sans-serif; }

.stApp { background: #0a0f1a; }

.metric-card {
    background: linear-gradient(135deg, #0e1825 0%, #152035 100%);
    border: 1px solid #1e3a5f;
    border-radius: 12px;
    padding: 16px 20px;
    text-align: center;
    margin-bottom: 8px;
}
.metric-card .label {
    color: #8bafc4;
    font-size: 0.75rem;
    font-weight: 500;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    margin-bottom: 4px;
}
.metric-card .value {
    font-size: 1.7rem;
    font-weight: 700;
    color: #e8f4fd;
}
.metric-card .value.ok   { color: #00e676; }
.metric-card .value.warn { color: #ff6b35; }

.panel-title {
    color: #c8dff0;
    font-size: 0.85rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    margin-bottom: 4px;
}
.slo-badge {
    display: inline-block;
    padding: 2px 8px;
    border-radius: 99px;
    font-size: 0.72rem;
    font-weight: 600;
    margin-left: 6px;
}
.slo-badge.ok   { background: rgba(0,230,118,0.15); color: #00e676; border: 1px solid #00e676; }
.slo-badge.warn { background: rgba(255,107,53,0.15); color: #ff6b35; border: 1px solid #ff6b35; }

.dashboard-header {
    background: linear-gradient(90deg, #00c8ff22 0%, #0040ff11 100%);
    border-bottom: 1px solid #1e3a5f;
    padding: 12px 0 8px 0;
    margin-bottom: 16px;
}
</style>
""", unsafe_allow_html=True)


# ── Data loading ──────────────────────────────────────────────────────────────
@st.cache_data(ttl=REFRESH_SECONDS)
def load_logs(path: Path) -> pd.DataFrame:
    records = []
    if path.exists():
        with path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    if not records:
        return pd.DataFrame()
    df = pd.json_normalize(records)
    if "ts" in df.columns:
        df["ts"] = pd.to_datetime(df["ts"], utc=True, errors="coerce")
    return df


def filter_time_range(df: pd.DataFrame, minutes: int) -> pd.DataFrame:
    if df.empty or "ts" not in df.columns:
        return df
    cutoff = datetime.now(tz=timezone.utc) - timedelta(minutes=minutes)
    return df[df["ts"] >= cutoff]


def plotly_base() -> dict:
    return dict(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="#0d1520",
        font=dict(family="Inter", color="#c8dff0", size=12),
        xaxis=dict(gridcolor=GRID_COLOR, zeroline=False, color="#6a8fa8"),
        yaxis=dict(gridcolor=GRID_COLOR, zeroline=False, color="#6a8fa8"),
        margin=dict(l=10, r=10, t=30, b=10),
        legend=dict(
            bgcolor="rgba(0,0,0,0)",
            font=dict(color="#c8dff0", size=11),
            orientation="h", y=1.1,
        ),
        hovermode="x unified",
    )


def slo_badge(ok: bool) -> str:
    label = "SLO ✓" if ok else "SLO ✗"
    cls = "ok" if ok else "warn"
    return f'<span class="slo-badge {cls}">{label}</span>'


def percentile(values: list, p: int) -> float:
    if not values:
        return 0.0
    items = sorted(values)
    idx = max(0, min(len(items) - 1, round((p / 100) * len(items) + 0.5) - 1))
    return float(items[idx])


# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## ⚙️ Controls")
    time_range = st.selectbox(
        "Time range",
        [15, 30, 60, 120, 240],
        index=2,
        format_func=lambda m: f"Last {m} min",
    )
    st.markdown("---")
    st.markdown("### 📋 SLO Targets")
    st.markdown(f"- Latency P95 ≤ **{SLO_LATENCY_P95} ms**")
    st.markdown(f"- Error rate ≤ **{SLO_ERROR_RATE}%**")
    st.markdown(f"- Quality score ≥ **{SLO_QUALITY}**")
    st.markdown(f"- Cost total ≤ **${SLO_COST_TOTAL}**")
    st.markdown(f"- Tokens total ≤ **{SLO_TOKENS_TOTAL:,}**")
    st.markdown("---")
    auto_refresh = st.checkbox("Auto-refresh", value=True)
    if auto_refresh:
        st.markdown(f"🔄 Refresh every **{REFRESH_SECONDS}s**")
        import time
        time.sleep(0)  # trigger rerun via st.rerun in loop below

    st.markdown("---")
    if st.button("🔄 Refresh now"):
        st.cache_data.clear()
        st.rerun()


# ── Header ────────────────────────────────────────────────────────────────────
st.markdown('<div class="dashboard-header">', unsafe_allow_html=True)
col_h1, col_h2 = st.columns([3, 1])
with col_h1:
    st.markdown("## 📊 Day 13 AI Observability Dashboard")
    st.markdown(f"<small style='color:#6a8fa8'>Source: `data/logs.jsonl` · Time range: last {time_range} min · Refresh: {REFRESH_SECONDS}s</small>", unsafe_allow_html=True)
with col_h2:
    st.markdown(f"<small style='color:#6a8fa8'>⏰ {datetime.now().strftime('%H:%M:%S')}</small>", unsafe_allow_html=True)
st.markdown('</div>', unsafe_allow_html=True)


# ── Load data ──────────────────────────────────────────────────────────────────
all_df = load_logs(LOGS_PATH)
df = filter_time_range(all_df, time_range)

if df.empty:
    st.warning(
        "⚠️ **Không có dữ liệu log.** "
        "Chạy API và load test để tạo dữ liệu:\n\n"
        "```bash\nuvicorn app.main:app --reload --env-file .env\n"
        "python scripts/load_test.py --concurrency 5\n```"
    )
    st.info("Dashboard vẫn hiển thị đầy đủ cấu trúc 6 panel. Dữ liệu sẽ xuất hiện sau khi chạy load test.")

# Separate event dataframes
resp_df = df[df.get("event", pd.Series(dtype=str)) == "response_sent"] if "event" in df.columns else pd.DataFrame()
req_df  = df[df.get("event", pd.Series(dtype=str)) == "request_received"] if "event" in df.columns else pd.DataFrame()
err_df  = df[df.get("event", pd.Series(dtype=str)) == "request_failed"] if "event" in df.columns else pd.DataFrame()


# ── Summary Metrics Row ────────────────────────────────────────────────────────
st.markdown("### 📈 Summary Metrics")
mc1, mc2, mc3, mc4, mc5, mc6 = st.columns(6)

# Latency P95
lat_vals = resp_df["latency_ms"].dropna().tolist() if "latency_ms" in resp_df.columns else []
p95 = percentile(lat_vals, 95)
p95_ok = p95 <= SLO_LATENCY_P95
mc1.markdown(f"""<div class="metric-card">
<div class="label">Latency P95</div>
<div class="value {'ok' if p95_ok else 'warn'}">{p95:.0f} ms</div>
</div>""", unsafe_allow_html=True)

# Traffic
total_req = len(req_df)
mc2.markdown(f"""<div class="metric-card">
<div class="label">Requests</div>
<div class="value ok">{total_req}</div>
</div>""", unsafe_allow_html=True)

# Error rate
err_rate = (len(err_df) / max(len(req_df), 1)) * 100 if not req_df.empty else 0.0
err_ok = err_rate <= SLO_ERROR_RATE
mc3.markdown(f"""<div class="metric-card">
<div class="label">Error Rate</div>
<div class="value {'ok' if err_ok else 'warn'}">{err_rate:.1f}%</div>
</div>""", unsafe_allow_html=True)

# Cost
cost_total = resp_df["cost_usd"].sum() if "cost_usd" in resp_df.columns and not resp_df.empty else 0.0
cost_ok = cost_total <= SLO_COST_TOTAL
mc4.markdown(f"""<div class="metric-card">
<div class="label">Cost Total</div>
<div class="value {'ok' if cost_ok else 'warn'}">${cost_total:.4f}</div>
</div>""", unsafe_allow_html=True)

# Tokens
tok_in  = int(resp_df["tokens_in"].sum())  if "tokens_in"  in resp_df.columns and not resp_df.empty else 0
tok_out = int(resp_df["tokens_out"].sum()) if "tokens_out" in resp_df.columns and not resp_df.empty else 0
tok_total = tok_in + tok_out
tok_ok = tok_total <= SLO_TOKENS_TOTAL
mc5.markdown(f"""<div class="metric-card">
<div class="label">Tokens Total</div>
<div class="value {'ok' if tok_ok else 'warn'}">{tok_total:,}</div>
</div>""", unsafe_allow_html=True)

# Quality
qual_avg = resp_df["quality_score"].mean() if "quality_score" in resp_df.columns and not resp_df.empty else 0.0
qual_ok = qual_avg >= SLO_QUALITY
mc6.markdown(f"""<div class="metric-card">
<div class="label">Quality Avg</div>
<div class="value {'ok' if qual_ok else 'warn'}">{qual_avg:.3f}</div>
</div>""", unsafe_allow_html=True)

st.markdown("---")

# ── Row 1: Latency | Traffic ───────────────────────────────────────────────────
col1, col2 = st.columns(2)

# Panel 1 — LATENCY
with col1:
    p50 = percentile(lat_vals, 50)
    p99 = percentile(lat_vals, 99)
    badge = slo_badge(p95_ok)
    st.markdown(f'<div class="panel-title">⏱ Latency Percentiles (ms) {badge}</div>', unsafe_allow_html=True)
    st.markdown(f"<small style='color:#6a8fa8'>P50={p50:.0f}ms · P95={p95:.0f}ms · P99={p99:.0f}ms · SLO threshold: P95 ≤ {SLO_LATENCY_P95}ms</small>", unsafe_allow_html=True)

    if not resp_df.empty and "ts" in resp_df.columns and "latency_ms" in resp_df.columns:
        lat_df = resp_df[["ts", "latency_ms"]].dropna().sort_values("ts")
        lat_df = lat_df.set_index("ts").resample("1min")["latency_ms"].agg(
            p50=lambda x: percentile(x.tolist(), 50),
            p95=lambda x: percentile(x.tolist(), 95),
            p99=lambda x: percentile(x.tolist(), 99),
        ).reset_index()

        fig = go.Figure()
        fig.add_trace(go.Scatter(x=lat_df["ts"], y=lat_df["p99"], name="P99",
                                  line=dict(color="#ff4f4f", width=1.5, dash="dot")))
        fig.add_trace(go.Scatter(x=lat_df["ts"], y=lat_df["p95"], name="P95",
                                  line=dict(color=WARN_COLOR, width=2)))
        fig.add_trace(go.Scatter(x=lat_df["ts"], y=lat_df["p50"], name="P50",
                                  line=dict(color=ACCENT, width=2)))
        # SLO line
        fig.add_hline(y=SLO_LATENCY_P95, line_dash="dash", line_color="#ff6b35",
                      annotation_text=f"SLO {SLO_LATENCY_P95}ms", annotation_position="top right",
                      annotation_font_color="#ff6b35")
        fig.update_layout(**plotly_base(), yaxis_title="ms")
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
    else:
        fig = go.Figure()
        fig.add_hline(y=SLO_LATENCY_P95, line_dash="dash", line_color="#ff6b35",
                      annotation_text=f"SLO {SLO_LATENCY_P95}ms")
        fig.update_layout(**plotly_base(), yaxis_title="ms",
                          title=dict(text="Chưa có dữ liệu", font=dict(color="#6a8fa8")))
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

# Panel 2 — TRAFFIC
with col2:
    st.markdown(f'<div class="panel-title">🚦 Request Traffic (req/min)</div>', unsafe_allow_html=True)
    st.markdown(f"<small style='color:#6a8fa8'>Total requests: {total_req} · SLO threshold: ≥ 1 req/min</small>", unsafe_allow_html=True)

    if not req_df.empty and "ts" in req_df.columns:
        traf_df = req_df[["ts"]].dropna().sort_values("ts")
        traf_df = traf_df.set_index("ts").resample("1min").size().reset_index(name="count")

        fig = go.Figure()
        fig.add_trace(go.Bar(x=traf_df["ts"], y=traf_df["count"],
                              name="Requests/min",
                              marker_color=ACCENT,
                              marker_line_width=0,
                              opacity=0.85))
        fig.add_hline(y=1, line_dash="dash", line_color=OK_COLOR,
                      annotation_text="SLO min 1 req/min", annotation_font_color=OK_COLOR)
        fig.update_layout(**plotly_base(), yaxis_title="requests/min")
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
    else:
        fig = go.Figure()
        fig.add_hline(y=1, line_dash="dash", line_color=OK_COLOR, annotation_text="SLO min 1 req/min")
        fig.update_layout(**plotly_base(), yaxis_title="requests/min",
                          title=dict(text="Chưa có dữ liệu", font=dict(color="#6a8fa8")))
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


# ── Row 2: Errors | Cost ───────────────────────────────────────────────────────
col3, col4 = st.columns(2)

# Panel 3 — ERRORS
with col3:
    badge = slo_badge(err_ok)
    st.markdown(f'<div class="panel-title">🔴 Error Rate & Breakdown {badge}</div>', unsafe_allow_html=True)
    st.markdown(f"<small style='color:#6a8fa8'>Error rate: {err_rate:.1f}% · SLO threshold: ≤ {SLO_ERROR_RATE}%</small>", unsafe_allow_html=True)

    if not req_df.empty and "ts" in req_df.columns:
        # Error rate over time
        all_events = pd.concat([
            req_df[["ts"]].assign(type="request"),
            err_df[["ts"]].assign(type="error") if not err_df.empty else pd.DataFrame(columns=["ts","type"]),
        ]).dropna(subset=["ts"]).sort_values("ts").set_index("ts")
        resampled = all_events.resample("1min")["type"].value_counts().unstack(fill_value=0)
        if "request" not in resampled.columns:
            resampled["request"] = 0
        if "error" not in resampled.columns:
            resampled["error"] = 0
        resampled["error_rate"] = resampled["error"] / resampled["request"].replace(0, 1) * 100
        resampled = resampled.reset_index()

        fig = go.Figure()
        fig.add_trace(go.Scatter(x=resampled["ts"], y=resampled["error_rate"],
                                  name="Error rate %",
                                  fill="tozeroy", fillcolor="rgba(255,75,75,0.1)",
                                  line=dict(color="#ff4f4f", width=2)))
        fig.add_hline(y=SLO_ERROR_RATE, line_dash="dash", line_color=WARN_COLOR,
                      annotation_text=f"SLO {SLO_ERROR_RATE}%", annotation_font_color=WARN_COLOR)
        fig.update_layout(**plotly_base(), yaxis_title="error rate %")
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

        # Error breakdown
        if not err_df.empty and "error_type" in err_df.columns:
            breakdown = err_df["error_type"].value_counts().reset_index()
            breakdown.columns = ["error_type", "count"]
            fig2 = px.bar(breakdown, x="error_type", y="count",
                          color_discrete_sequence=["#ff6b35"],
                          labels={"error_type": "Type", "count": "Count"})
            fig2.update_layout(**plotly_base(), yaxis_title="count", height=150,
                               margin=dict(t=5, b=5, l=5, r=5))
            st.plotly_chart(fig2, use_container_width=True, config={"displayModeBar": False})
        else:
            st.markdown("<small style='color:#6a8fa8'>Chưa có lỗi nào trong khoảng thời gian này ✅</small>", unsafe_allow_html=True)
    else:
        fig = go.Figure()
        fig.add_hline(y=SLO_ERROR_RATE, line_dash="dash", line_color=WARN_COLOR,
                      annotation_text=f"SLO {SLO_ERROR_RATE}%")
        fig.update_layout(**plotly_base(), yaxis_title="error rate %",
                          title=dict(text="Chưa có dữ liệu", font=dict(color="#6a8fa8")))
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

# Panel 4 — COST
with col4:
    badge = slo_badge(cost_ok)
    st.markdown(f'<div class="panel-title">💰 Cost Over Time (USD) {badge}</div>', unsafe_allow_html=True)
    st.markdown(f"<small style='color:#6a8fa8'>Total: ${cost_total:.4f} · SLO threshold: ≤ ${SLO_COST_TOTAL}</small>", unsafe_allow_html=True)

    if not resp_df.empty and "ts" in resp_df.columns and "cost_usd" in resp_df.columns:
        cost_df = resp_df[["ts", "cost_usd"]].dropna().sort_values("ts")
        cost_by_min = cost_df.set_index("ts").resample("1min")["cost_usd"].sum().reset_index()
        cost_by_min["cumulative"] = cost_by_min["cost_usd"].cumsum()

        fig = go.Figure()
        fig.add_trace(go.Bar(x=cost_by_min["ts"], y=cost_by_min["cost_usd"],
                              name="Cost/min", marker_color="#a78bfa", opacity=0.75))
        fig.add_trace(go.Scatter(x=cost_by_min["ts"], y=cost_by_min["cumulative"],
                                  name="Cumulative", yaxis="y2",
                                  line=dict(color="#f59e0b", width=2)))
        layout = plotly_base()
        layout["yaxis2"] = dict(overlaying="y", side="right", gridcolor=GRID_COLOR,
                                color="#6a8fa8", title="cumulative USD")
        fig.add_hline(y=SLO_COST_TOTAL, line_dash="dash", line_color=WARN_COLOR,
                      annotation_text=f"SLO ${SLO_COST_TOTAL}", annotation_font_color=WARN_COLOR)
        fig.update_layout(**layout, yaxis_title="USD/min")
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
    else:
        fig = go.Figure()
        fig.add_hline(y=SLO_COST_TOTAL, line_dash="dash", line_color=WARN_COLOR,
                      annotation_text=f"SLO ${SLO_COST_TOTAL}")
        fig.update_layout(**plotly_base(), yaxis_title="USD/min",
                          title=dict(text="Chưa có dữ liệu", font=dict(color="#6a8fa8")))
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


# ── Row 3: Tokens | Quality ────────────────────────────────────────────────────
col5, col6 = st.columns(2)

# Panel 5 — TOKENS
with col5:
    badge = slo_badge(tok_ok)
    st.markdown(f'<div class="panel-title">🔢 Input & Output Tokens {badge}</div>', unsafe_allow_html=True)
    st.markdown(f"<small style='color:#6a8fa8'>tokens_in={tok_in:,} · tokens_out={tok_out:,} · total={tok_total:,} · SLO ≤ {SLO_TOKENS_TOTAL:,}</small>", unsafe_allow_html=True)

    if not resp_df.empty and "ts" in resp_df.columns and "tokens_in" in resp_df.columns:
        tok_df = resp_df[["ts", "tokens_in", "tokens_out"]].dropna().sort_values("ts")
        tok_by_min = tok_df.set_index("ts").resample("1min").sum().reset_index()

        fig = go.Figure()
        fig.add_trace(go.Bar(x=tok_by_min["ts"], y=tok_by_min["tokens_in"],
                              name="tokens_in", marker_color="#38bdf8"))
        fig.add_trace(go.Bar(x=tok_by_min["ts"], y=tok_by_min["tokens_out"],
                              name="tokens_out", marker_color="#818cf8"))
        fig.add_hline(y=SLO_TOKENS_TOTAL / 60, line_dash="dash", line_color=WARN_COLOR,
                      annotation_text=f"SLO rate", annotation_font_color=WARN_COLOR)
        fig.update_layout(**plotly_base(), barmode="stack", yaxis_title="tokens")
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
    else:
        fig = go.Figure()
        fig.update_layout(**plotly_base(), yaxis_title="tokens",
                          title=dict(text="Chưa có dữ liệu", font=dict(color="#6a8fa8")))
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

# Panel 6 — QUALITY
with col6:
    badge = slo_badge(qual_ok)
    st.markdown(f'<div class="panel-title">⭐ Quality Proxy (score 0–1) {badge}</div>', unsafe_allow_html=True)
    st.markdown(f"<small style='color:#6a8fa8'>mean={qual_avg:.3f} · SLO threshold: ≥ {SLO_QUALITY}</small>", unsafe_allow_html=True)

    if not resp_df.empty and "ts" in resp_df.columns and "quality_score" in resp_df.columns:
        qual_df = resp_df[["ts", "quality_score"]].dropna().sort_values("ts")
        qual_by_min = qual_df.set_index("ts").resample("1min")["quality_score"].mean().reset_index()

        fig = go.Figure()
        fig.add_trace(go.Scatter(x=qual_by_min["ts"], y=qual_by_min["quality_score"],
                                  name="Quality avg",
                                  fill="tozeroy", fillcolor="rgba(0,200,118,0.08)",
                                  line=dict(color=OK_COLOR, width=2)))
        fig.add_hline(y=SLO_QUALITY, line_dash="dash", line_color=WARN_COLOR,
                      annotation_text=f"SLO {SLO_QUALITY}", annotation_font_color=WARN_COLOR)
        fig.update_layout(**plotly_base(), yaxis_title="quality score",
                          yaxis=dict(range=[0, 1.05], gridcolor=GRID_COLOR, color="#6a8fa8"))
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
    else:
        fig = go.Figure()
        fig.add_hline(y=SLO_QUALITY, line_dash="dash", line_color=WARN_COLOR,
                      annotation_text=f"SLO {SLO_QUALITY}")
        fig.update_layout(**plotly_base(), yaxis_title="quality score",
                          yaxis=dict(range=[0, 1.05]),
                          title=dict(text="Chưa có dữ liệu", font=dict(color="#6a8fa8")))
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


# ── Footer ─────────────────────────────────────────────────────────────────────
st.markdown("---")
st.markdown(
    f"<small style='color:#3a5f80'>📂 Source: `{LOGS_PATH}` · "
    f"Schema: `config/dashboard.yaml` · "
    f"SLO: `config/slo.yaml` · "
    f"Alerts: `config/alert_rules.yaml`</small>",
    unsafe_allow_html=True,
)

# ── Auto-refresh ───────────────────────────────────────────────────────────────
if auto_refresh:
    import time
    time.sleep(REFRESH_SECONDS)
    st.rerun()
