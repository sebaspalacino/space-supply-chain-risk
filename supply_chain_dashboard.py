"""
supply_chain_dashboard.py
─────────────────────────
Space Supply Chain Risk Dashboard
Run:
    py -m streamlit run supply_chain_dashboard.py
"""

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from pathlib import Path

# ─────────────────────────────────────────────────────────────────────────────
# Page config
# ─────────────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Space Supply Chain Risk Intelligence",
    page_icon="🛰️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─────────────────────────────────────────────────────────────────────────────
# CSS
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
  @import url('https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=DM+Sans:wght@300;400;500;600&display=swap');
  :root {
    --bg:#0b0f1a; --surface:#111827; --border:#1e2d45;
    --accent:#00d4ff; --text:#e2e8f0; --muted:#64748b;
  }
  html,body,[class*="css"]{background-color:var(--bg)!important;color:var(--text)!important;font-family:'DM Sans',sans-serif;}
  section[data-testid="stSidebar"]{background:var(--surface)!important;border-right:1px solid var(--border);}
  h1,h2,h3{font-family:'Space Mono',monospace!important;}
  h1{color:var(--accent)!important;letter-spacing:-1px;}
  h2{color:var(--text)!important;font-size:1.1rem!important;letter-spacing:.05em;text-transform:uppercase;}
  [data-testid="stMetric"]{background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:1rem 1.2rem;}
  [data-testid="stMetricLabel"]{color:var(--muted)!important;font-size:.75rem!important;text-transform:uppercase;letter-spacing:.08em;}
  [data-testid="stMetricValue"]{color:var(--accent)!important;font-family:'Space Mono',monospace!important;}
  button[data-baseweb="tab"]{font-family:'Space Mono',monospace!important;font-size:.78rem!important;color:var(--muted)!important;border-bottom:2px solid transparent!important;}
  button[data-baseweb="tab"][aria-selected="true"]{color:var(--accent)!important;border-bottom:2px solid var(--accent)!important;}
  hr{border-color:var(--border)!important;}
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# Plotly theme — kept minimal to avoid Plotly 6 phantom "undefined" label.
# title_font, colorway, legend are set per-chart to avoid duplicate-key errors.
# ─────────────────────────────────────────────────────────────────────────────
PLOTLY_THEME = dict(
    paper_bgcolor="#0b0f1a",
    plot_bgcolor="#111827",
    font=dict(family="DM Sans", color="#e2e8f0", size=12),
)

COLORWAY = ["#00d4ff", "#ff6b35", "#7c3aed", "#10b981", "#f59e0b", "#ef4444", "#ec4899", "#06b6d4"]

# Reusable axis grid style
AXIS = dict(gridcolor="#1e2d45", linecolor="#1e2d45", zerolinecolor="#1e2d45")

TITLE_FONT = dict(family="Space Mono", color="#00d4ff", size=14)

SEV_COLORS = ["#10b981", "#84cc16", "#f59e0b", "#f97316", "#ef4444"]


# ─────────────────────────────────────────────────────────────────────────────
# Severity cell coloring — no matplotlib needed
# ─────────────────────────────────────────────────────────────────────────────
def color_severity(val):
    colors = {1: "#064e3b", 2: "#365314", 3: "#78350f", 4: "#7c2d12", 5: "#450a0a"}
    try:
        return f"background-color: {colors.get(int(val), '#111827')}; color: #e2e8f0"
    except (ValueError, TypeError):
        return ""


def style_df(df, sev_col="Sev"):
    if sev_col in df.columns:
        return df.style.map(color_severity, subset=[sev_col])
    return df.style


# ─────────────────────────────────────────────────────────────────────────────
# Data loading
# ─────────────────────────────────────────────────────────────────────────────
@st.cache_data
def load_data(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    df["severity_score"] = pd.to_numeric(df["severity_score"], errors="coerce").fillna(1).astype(int)
    df["filing_date"]    = pd.to_datetime(df["filing_date"], errors="coerce")
    df["filing_year"]    = df["filing_year"].astype(str)
    df["company_short"]  = (
        df["company"]
        .str.replace(r"\b(Technologies|Corporation|Industries|Holdings|Global|Systems)\b", "", regex=True)
        .str.strip()
    )
    return df


CSV_NAME = "master_risk_table_validated.csv"
csv_path = Path(__file__).parent / CSV_NAME

if not csv_path.exists():
    st.sidebar.warning(f"⚠ `{CSV_NAME}` not found next to this script.")
    uploaded = st.sidebar.file_uploader("Upload your validated CSV", type="csv")
    if uploaded:
        df = pd.read_csv(uploaded)
        df["severity_score"] = pd.to_numeric(df["severity_score"], errors="coerce").fillna(1).astype(int)
        df["filing_date"]    = pd.to_datetime(df["filing_date"], errors="coerce")
        df["filing_year"]    = df["filing_year"].astype(str)
        df["company_short"]  = (
            df["company"]
            .str.replace(r"\b(Technologies|Corporation|Industries|Holdings|Global|Systems)\b", "", regex=True)
            .str.strip()
        )
    else:
        st.info("👆 Upload `master_risk_table_validated.csv` to begin.")
        st.stop()
else:
    df = load_data(str(csv_path))

# ─────────────────────────────────────────────────────────────────────────────
# Sidebar filters
# ─────────────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🛰️ RISK INTELLIGENCE")
    st.markdown("**Space Supply Chain Dashboard**")
    st.markdown("---")
    st.markdown("### FILTERS")

    sel_companies = st.multiselect(
        "Companies", sorted(df["company"].unique()),
        default=sorted(df["company"].unique()),
    )
    sel_categories = st.multiselect(
        "Risk Categories", sorted(df["risk_category"].unique()),
        default=sorted(df["risk_category"].unique()),
    )
    sev_range = st.slider("Severity Score", 1, 5, (1, 5))

    conf_opts = sorted(df["llm_confidence"].dropna().unique()) if "llm_confidence" in df.columns else []
    sel_conf  = st.multiselect("LLM Confidence", conf_opts, default=conf_opts) if conf_opts else []

    st.markdown("---")
    st.markdown(
        "<span style='color:#64748b;font-size:.72rem;font-family:Space Mono'>"
        "SEC EDGAR 10-K · FY2025</span>",
        unsafe_allow_html=True,
    )

# Apply filters
mask = (
    df["company"].isin(sel_companies) &
    df["risk_category"].isin(sel_categories) &
    df["severity_score"].between(sev_range[0], sev_range[1])
)
if sel_conf and "llm_confidence" in df.columns:
    mask &= df["llm_confidence"].isin(sel_conf)
dff = df[mask].copy()

# ─────────────────────────────────────────────────────────────────────────────
# Header + KPIs
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("# Space Supply Chain Risk Intelligence")
st.markdown(
    "<p style='color:#64748b;margin-top:-12px;margin-bottom:20px;font-size:.85rem'>"
    "FY2025 · SEC EDGAR 10-K Analysis </p>",
    unsafe_allow_html=True,
)

k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Total Risk Signals", f"{len(dff):,}")
k2.metric("Companies",          f"{dff['company'].nunique()}")
k3.metric("Risk Categories",    f"{dff['risk_category'].nunique()}")
k4.metric("Avg Severity",       f"{dff['severity_score'].mean():.2f} / 5")
k5.metric("Critical (Sev 5)",   f"{(dff['severity_score']==5).sum()}")

st.markdown("---")

# ─────────────────────────────────────────────────────────────────────────────
# Tabs
# ─────────────────────────────────────────────────────────────────────────────
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "🔥 Risk Heatmap",
    "🌐 Geopolitical Risk",
    "🔗 Single-Source Analysis",
    "📅 Disruption Timeline",
    "🔎 Evidence Explorer",
])


# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — RISK HEATMAP
# ══════════════════════════════════════════════════════════════════════════════
with tab1:
    st.markdown("## Risk Heatmap — Company × Category")
    st.markdown(
        "<p style='color:#64748b;font-size:.82rem'>Average severity per company per risk category. "
        "Darker red = higher exposure.</p>", unsafe_allow_html=True,
    )

    col_chart, col_ctrl = st.columns([3, 1])
    with col_ctrl:
        heatmap_metric = st.radio("Metric", ["Avg Severity", "Count of Signals"], index=0)

    agg_fn = "mean" if heatmap_metric == "Avg Severity" else "count"
    pivot = dff.pivot_table(
        index="company_short", columns="risk_category",
        values="severity_score", aggfunc=agg_fn,
    ).round(2)
    pivot = pivot.loc[pivot.sum(axis=1).sort_values(ascending=False).index]

    fig_heat = go.Figure(go.Heatmap(
        z=pivot.values,
        x=[c.replace(" & ", " &\n") for c in pivot.columns],
        y=pivot.index,
        colorscale=[
            [0.0, "#111827"], [0.25, "#1e3a5f"],
            [0.5, "#1d4ed8"], [0.75, "#f97316"], [1.0, "#ef4444"],
        ],
        hoverongaps=False,
        hovertemplate="<b>%{y}</b><br>%{x}<br>Value: %{z:.2f}<extra></extra>",
        colorbar=dict(
            title=dict(text="Score", font=dict(color="#64748b", size=11)),
            tickfont=dict(color="#64748b"),
            bgcolor="#111827", bordercolor="#1e2d45",
        ),
        text=pivot.values.round(1),
        texttemplate="%{text}",
        textfont=dict(size=11, color="white"),
    ))
    fig_heat.update_layout(
        **PLOTLY_THEME,
        title_font=TITLE_FONT,
        height=420,
        margin=dict(l=10, r=10, t=20, b=60),
        xaxis=dict(**AXIS, tickangle=-30, tickfont=dict(size=10)),
        yaxis=dict(**AXIS, tickfont=dict(size=11)),
    )
    with col_chart:
        st.plotly_chart(fig_heat, use_container_width=True)

    st.markdown("#### Severity Distribution by Company")
    sev_piv = dff.groupby(["company_short", "severity_score"]).size().reset_index(name="count")
    fig_sev = px.bar(
        sev_piv, x="company_short", y="count", color="severity_score",
        color_continuous_scale=SEV_COLORS,
        labels={"company_short": "", "count": "Signals", "severity_score": "Severity"},
        barmode="stack",
    )
    fig_sev.update_layout(
        **PLOTLY_THEME,
        title_font=TITLE_FONT,
        colorway=COLORWAY,
        height=280,
        margin=dict(l=10, r=10, t=10, b=10),
        showlegend=True,
        legend=dict(orientation="h", y=-0.25, font=dict(color="#e2e8f0", size=10)),
        coloraxis_showscale=False,
        xaxis=dict(**AXIS),
        yaxis=dict(**AXIS),
    )
    st.plotly_chart(fig_sev, use_container_width=True)


# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — GEOPOLITICAL RISK DEEP DIVE
# ══════════════════════════════════════════════════════════════════════════════
with tab2:
    st.markdown("## Geopolitical Risk Deep Dive")
    st.markdown(
        "<p style='color:#64748b;font-size:.82rem'>Breakdown of geopolitical risk signals by company, "
        "subcategory, keyword, and severity.</p>", unsafe_allow_html=True,
    )

    geo_df = dff[dff["risk_category"] == "Geopolitical Risk"].copy()

    if len(geo_df) == 0:
        st.info("No Geopolitical Risk signals in the current filter selection.")
    else:
        col_g1, col_g2 = st.columns(2)

        with col_g1:
            st.markdown("#### Signals by Company & Subcategory")
            geo_grp = geo_df.groupby(["company_short", "risk_subcategory"]).size().reset_index(name="count")
            fig_geo_bar = px.bar(
                geo_grp, x="count", y="company_short", color="risk_subcategory",
                orientation="h", barmode="stack",
                labels={"count": "Signals", "company_short": "", "risk_subcategory": "Subcategory"},
                color_discrete_sequence=COLORWAY,
            )
            fig_geo_bar.update_layout(
                **PLOTLY_THEME,
                title_font=TITLE_FONT,
                colorway=COLORWAY,
                height=380,
                margin=dict(l=10, r=10, t=10, b=10),
                showlegend=True,
                legend=dict(orientation="h", y=-0.3, font=dict(color="#e2e8f0", size=9)),
                xaxis=dict(**AXIS, title="Number of Signals"),
                yaxis=dict(**AXIS),
            )
            st.plotly_chart(fig_geo_bar, use_container_width=True)

        with col_g2:
            st.markdown("#### Top Keywords by Frequency")
            kw_grp = geo_df.groupby("keyword_matched").agg(
                count=("severity_score", "count"),
                avg_sev=("severity_score", "mean"),
            ).reset_index().sort_values("count", ascending=True).tail(15)

            fig_kw = go.Figure(go.Bar(
                x=kw_grp["count"], y=kw_grp["keyword_matched"],
                orientation="h",
                marker=dict(
                    color=kw_grp["avg_sev"],
                    colorscale=["#10b981", "#f59e0b", "#ef4444"],
                    cmin=1, cmax=5,
                    colorbar=dict(
                        title="Avg Sev",
                        tickfont=dict(color="#64748b"),
                        len=0.6,
                    ),
                ),
                text=kw_grp["count"], textposition="outside",
                textfont=dict(color="#e2e8f0", size=11),
                hovertemplate="<b>%{y}</b><br>Count: %{x}<extra></extra>",
            ))
            fig_kw.update_layout(
                **PLOTLY_THEME,
                title_font=TITLE_FONT,
                height=380,
                margin=dict(l=10, r=80, t=10, b=10),
                xaxis=dict(**AXIS, title="Mentions"),
                yaxis=dict(**AXIS, tickfont=dict(size=10)),
            )
            st.plotly_chart(fig_kw, use_container_width=True)

        col_g3, col_g4 = st.columns(2)

        with col_g3:
            st.markdown("#### Severity Distribution")
            sev_geo = geo_df.groupby("severity_score").size().reset_index(name="count")
            fig_sev_geo = px.pie(
                sev_geo, values="count", names="severity_score",
                color="severity_score",
                color_discrete_map={1:"#10b981",2:"#84cc16",3:"#f59e0b",4:"#f97316",5:"#ef4444"},
                hole=0.5,
            )
            fig_sev_geo.update_traces(
                textposition="outside",
                textfont=dict(color="#e2e8f0"),
                hovertemplate="Severity %{label}<br>Count: %{value}<extra></extra>",
            )
            fig_sev_geo.update_layout(
                **PLOTLY_THEME,
                title_font=TITLE_FONT,
                coloraxis_showscale=False,
                height=300,
                margin=dict(l=10, r=10, t=10, b=10),
                showlegend=True,
                legend=dict(orientation="h", y=-0.15, font=dict(color="#e2e8f0", size=10)),
            )
            st.plotly_chart(fig_sev_geo, use_container_width=True)

        with col_g4:
            st.markdown("#### Avg Severity by Subcategory")
            sub_sev = geo_df.groupby("risk_subcategory").agg(
                avg_sev=("severity_score", "mean"),
                count=("severity_score", "count"),
            ).reset_index().sort_values("avg_sev", ascending=False)

            fig_sub_sev = go.Figure(go.Bar(
                x=sub_sev["risk_subcategory"],
                y=sub_sev["avg_sev"],
                marker=dict(
                    color=sub_sev["avg_sev"],
                    colorscale=["#10b981", "#f59e0b", "#ef4444"],
                    cmin=1, cmax=5,
                    showscale=False,
                ),
                text=sub_sev["avg_sev"].round(2),
                textposition="outside",
                textfont=dict(color="#e2e8f0", size=10),
                hovertemplate="<b>%{x}</b><br>Avg Severity: %{y:.2f}<extra></extra>",
            ))
            fig_sub_sev.update_layout(
                **PLOTLY_THEME,
                title_font=TITLE_FONT,
                height=300,
                margin=dict(l=10, r=10, t=10, b=80),
                xaxis=dict(**AXIS, tickangle=-30, tickfont=dict(size=9)),
                yaxis=dict(**AXIS, range=[0, 5.5], title="Avg Severity"),
            )
            st.plotly_chart(fig_sub_sev, use_container_width=True)

        st.markdown("#### Geopolitical Risk Evidence")
        geo_ev = geo_df[["company", "risk_subcategory", "keyword_matched",
                          "severity_score", "evidence_sentence"]].copy()
        geo_ev.columns = ["Company", "Subcategory", "Keyword", "Sev", "Evidence Sentence"]
        geo_ev = geo_ev.sort_values("Sev", ascending=False)
        st.dataframe(
            style_df(geo_ev, "Sev"),
            use_container_width=True, hide_index=True, height=320,
            column_config={"Evidence Sentence": st.column_config.TextColumn(width="large")},
        )


# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 — SINGLE-SOURCE ANALYSIS
# ══════════════════════════════════════════════════════════════════════════════
with tab3:
    st.markdown("## Supplier Concentration Analysis")
    st.markdown(
        "<p style='color:#64748b;font-size:.82rem'>Single-source, sole-source, and "
        "supplier dependency signals across companies.</p>", unsafe_allow_html=True,
    )

    supplier_df = dff[dff["risk_category"] == "Supplier Concentration"].copy()

    if len(supplier_df) == 0:
        st.info("No Supplier Concentration signals in current filter selection.")
    else:
        col_a, col_b = st.columns(2)

        with col_a:
            sup_grp = supplier_df.groupby(
                ["company_short", "risk_subcategory"]
            ).size().reset_index(name="count")
            fig_sup = px.bar(
                sup_grp, x="company_short", y="count", color="risk_subcategory",
                barmode="stack",
                labels={"company_short": "", "count": "Risk Signals", "risk_subcategory": "Type"},
                color_discrete_sequence=COLORWAY,
                title="Supplier Risk Signals by Company",
            )
            fig_sup.update_layout(
                **PLOTLY_THEME,
                title_font=TITLE_FONT,
                colorway=COLORWAY,
                height=350,
                margin=dict(l=10, r=10, t=40, b=10),
                showlegend=True,
                legend=dict(orientation="h", y=-0.3, font=dict(color="#e2e8f0", size=10)),
                xaxis=dict(**AXIS, tickangle=-20),
                yaxis=dict(**AXIS),
            )
            st.plotly_chart(fig_sup, use_container_width=True)

        with col_b:
            sup_sev = supplier_df.groupby("company_short").agg(
                avg_severity=("severity_score", "mean"),
            ).reset_index().sort_values("avg_severity", ascending=False)

            fig_sup_sev = go.Figure(go.Bar(
                x=sup_sev["company_short"], y=sup_sev["avg_severity"],
                marker=dict(
                    color=sup_sev["avg_severity"],
                    colorscale=["#10b981", "#f59e0b", "#ef4444"],
                    cmin=1, cmax=5,
                    showscale=False,
                ),
                text=sup_sev["avg_severity"].round(2),
                textposition="outside",
                textfont=dict(color="#e2e8f0", size=11),
                hovertemplate="<b>%{x}</b><br>Avg Severity: %{y:.2f}<extra></extra>",
            ))
            fig_sup_sev.update_layout(
                **PLOTLY_THEME,
                title_font=TITLE_FONT,
                title=dict(text="Avg Supplier Risk Severity", font=TITLE_FONT),
                height=350,
                margin=dict(l=10, r=10, t=40, b=10),
                xaxis=dict(**AXIS, tickangle=-20),
                yaxis=dict(**AXIS, range=[0, 5.5], title="Avg Severity Score"),
            )
            st.plotly_chart(fig_sup_sev, use_container_width=True)

        st.markdown("#### Supplier Concentration Evidence")
        subcat_filter = st.multiselect(
            "Filter by subcategory",
            options=sorted(supplier_df["risk_subcategory"].unique()),
            default=sorted(supplier_df["risk_subcategory"].unique()),
            key="supplier_subcat",
        )
        sup_ev = supplier_df[supplier_df["risk_subcategory"].isin(subcat_filter)][
            ["company", "risk_subcategory", "keyword_matched", "severity_score", "evidence_sentence"]
        ].copy()
        sup_ev.columns = ["Company", "Subcategory", "Keyword", "Sev", "Evidence Sentence"]
        sup_ev = sup_ev.sort_values("Sev", ascending=False)
        st.dataframe(
            style_df(sup_ev, "Sev"),
            use_container_width=True, hide_index=True,
            column_config={"Evidence Sentence": st.column_config.TextColumn(width="large")},
        )


# ══════════════════════════════════════════════════════════════════════════════
# TAB 4 — DISRUPTION TIMELINE
# ══════════════════════════════════════════════════════════════════════════════
with tab4:
    st.markdown("## Disruption Risk Timeline")
    st.markdown(
        "<p style='color:#64748b;font-size:.82rem'>Risk signal volume by filing date and grouping.</p>",
        unsafe_allow_html=True,
    )

    timeline_df = dff.copy()
    timeline_df["filing_date_str"] = timeline_df["filing_date"].dt.strftime("%b %d, %Y")

    _, col_t1 = st.columns([2, 1])
    with col_t1:
        timeline_group = st.radio(
            "Group signals by",
            ["Risk Category", "Company", "Severity Score"],
            index=0, key="timeline_group",
        )

    gcol = {"Risk Category": "risk_category",
            "Company":       "company_short",
            "Severity Score":"severity_score"}[timeline_group]

    tl = timeline_df.groupby(["filing_date", gcol]).size().reset_index(name="count")
    tl = tl.sort_values("filing_date")

    fig_tl = px.scatter(
        tl, x="filing_date", y="count", color=gcol,
        size="count", size_max=40,
        labels={"filing_date": "Filing Date", "count": "Risk Signals", gcol: timeline_group},
        color_discrete_sequence=COLORWAY,
    )
    fig_tl.update_layout(
        **PLOTLY_THEME,
        title_font=TITLE_FONT,
        colorway=COLORWAY,
        height=360,
        margin=dict(l=10, r=10, t=20, b=10),
        showlegend=True,
        legend=dict(orientation="h", y=-0.25, font=dict(color="#e2e8f0", size=10)),
        xaxis=dict(**AXIS),
        yaxis=dict(**AXIS),
    )
    st.plotly_chart(fig_tl, use_container_width=True)

    st.markdown("#### Filing Date Summary")
    date_sum = timeline_df.groupby(["company", "filing_date_str"]).agg(
        total_signals=("severity_score", "count"),
        avg_severity=("severity_score", "mean"),
        categories=("risk_category", lambda x: ", ".join(sorted(x.unique()))),
    ).reset_index().sort_values("filing_date_str")
    date_sum.columns = ["Company", "Filing Date", "Total Signals", "Avg Severity", "Categories"]
    st.dataframe(date_sum, use_container_width=True, hide_index=True)

    st.markdown("#### Risk Category Volume Ranking")
    cat_rank = timeline_df.groupby("risk_category").agg(
        signals=("severity_score", "count"),
        avg_sev=("severity_score", "mean"),
    ).reset_index().sort_values("signals", ascending=False)

    fig_rank = go.Figure()
    fig_rank.add_trace(go.Bar(
        name="Signal Count",
        x=cat_rank["risk_category"], y=cat_rank["signals"],
        marker_color="#00d4ff", yaxis="y",
        hovertemplate="<b>%{x}</b><br>Signals: %{y}<extra></extra>",
    ))
    fig_rank.add_trace(go.Scatter(
        name="Avg Severity",
        x=cat_rank["risk_category"], y=cat_rank["avg_sev"],
        mode="lines+markers",
        marker=dict(color="#ff6b35", size=9, symbol="diamond"),
        line=dict(color="#ff6b35", width=2, dash="dot"),
        yaxis="y2",
        hovertemplate="<b>%{x}</b><br>Avg Severity: %{y:.2f}<extra></extra>",
    ))
    fig_rank.update_layout(
        **PLOTLY_THEME,
        title_font=TITLE_FONT,
        height=300,
        margin=dict(l=10, r=60, t=10, b=60),
        showlegend=True,
        legend=dict(orientation="h", y=-0.4, font=dict(color="#e2e8f0", size=10)),
        xaxis=dict(**AXIS, tickangle=-25, tickfont=dict(size=10)),
        yaxis=dict(**AXIS, title="Signal Count", color="#00d4ff"),
        yaxis2=dict(
            title="Avg Severity", color="#ff6b35",
            overlaying="y", side="right", range=[0, 5.5],
            gridcolor="#1e2d45", linecolor="#1e2d45",
        ),
        barmode="group",
    )
    st.plotly_chart(fig_rank, use_container_width=True)


# ══════════════════════════════════════════════════════════════════════════════
# TAB 5 — EVIDENCE EXPLORER
# ══════════════════════════════════════════════════════════════════════════════
with tab5:
    st.markdown("## Evidence Explorer")
    st.markdown(
        "<p style='color:#64748b;font-size:.82rem'>Search and filter all validated risk sentences. "
        "Export any view as CSV.</p>", unsafe_allow_html=True,
    )

    search_term = st.text_input(
        "🔍 Search evidence sentences",
        placeholder="e.g. sole source, rare earth, export license...",
    )

    col_e1, col_e2, col_e3 = st.columns(3)
    with col_e1:
        ev_cats = st.multiselect(
            "Risk Category", sorted(dff["risk_category"].unique()),
            default=sorted(dff["risk_category"].unique()), key="ev_cat",
        )
    with col_e2:
        ev_sev = st.multiselect("Severity", [1,2,3,4,5], default=[1,2,3,4,5], key="ev_sev")
    with col_e3:
        ev_sort = st.selectbox(
            "Sort by", ["Severity ↓", "Severity ↑", "Company A–Z", "Category A–Z"]
        )

    ev_df = dff[dff["risk_category"].isin(ev_cats) & dff["severity_score"].isin(ev_sev)].copy()

    if search_term:
        ev_df = ev_df[
            ev_df["evidence_sentence"].str.contains(search_term, case=False, na=False) |
            ev_df["keyword_matched"].str.contains(search_term, case=False, na=False)
        ]

    sort_col, sort_asc = {
        "Severity ↓":   ("severity_score", False),
        "Severity ↑":   ("severity_score", True),
        "Company A–Z":  ("company", True),
        "Category A–Z": ("risk_category", True),
    }[ev_sort]
    ev_df = ev_df.sort_values(sort_col, ascending=sort_asc)

    st.markdown(f"**{len(ev_df):,} signals** match current filters")

    display_cols = [c for c in [
        "company", "risk_category", "risk_subcategory",
        "keyword_matched", "severity_score", "llm_confidence", "evidence_sentence",
    ] if c in ev_df.columns]

    ev_display = ev_df[display_cols].rename(columns={
        "company":          "Company",
        "risk_category":    "Category",
        "risk_subcategory": "Subcategory",
        "keyword_matched":  "Keyword",
        "severity_score":   "Sev",
        "llm_confidence":   "Confidence",
        "evidence_sentence":"Evidence Sentence",
    })

    st.dataframe(
        style_df(ev_display, "Sev"),
        use_container_width=True, hide_index=True, height=480,
        column_config={
            "Evidence Sentence": st.column_config.TextColumn(width="large"),
            "Sev": st.column_config.NumberColumn(format="%d ⬤"),
        },
    )

    csv_export = ev_display.to_csv(index=False).encode("utf-8")
    st.download_button(
        label="⬇ Download filtered CSV",
        data=csv_export,
        file_name="supply_chain_risk_filtered.csv",
        mime="text/csv",
    )