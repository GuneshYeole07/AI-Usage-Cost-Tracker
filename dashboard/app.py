"""Streamlit dashboard for the LLM Token Auditor (talks to the FastAPI backend).

Design: big bold type, one row of tabs at the top, every action is one click.
"""

from __future__ import annotations

import html
import os

import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st

# 127.0.0.1, not "localhost": on Windows "localhost" tries IPv6 first and adds ~2s to every request.
API = os.environ.get("BACKEND_API_URL", "http://127.0.0.1:8000").rstrip("/")
HTTP = requests.Session()

# Two colours, one meaning each, on every page: blue = useful, orange = avoidable.
INK, USEFUL, WASTE, MUTED, GRID, PAPER = "#0b0b0b", "#2a78d6", "#eb6834", "#52514e", "#e6e4de", "#fcfcfb"
FONT = "'Segoe UI', system-ui, -apple-system, 'Helvetica Neue', Arial, sans-serif"
PAGES = ["Overview", "Sessions", "Team", "Forecast", "Check rules", "Add data"]

st.set_page_config(page_title="LLM Token Auditor", page_icon="🔍", layout="wide", initial_sidebar_state="collapsed")

st.markdown(
    f"""
<style>
html, body, [class*="css"], .stMarkdown, button, input, textarea, select {{ font-family: {FONT} !important; }}
[data-testid="stSidebar"], [data-testid="collapsedControl"], [data-testid="stSidebarCollapsedControl"],
[data-testid="stDecoration"], [data-testid="stAppDeployButton"], #MainMenu,
header[data-testid="stHeader"] {{ display: none !important; }}
.block-container {{ padding-top: 1.8rem !important; max-width: 1280px; }}
h1, h2, h3 {{ color: {INK}; letter-spacing: -0.02em; }}
h1 {{ font-weight: 900 !important; font-size: 2.6rem !important; line-height: 1.1 !important; }}
h2 {{ font-weight: 850 !important; font-size: 1.7rem !important; }}
h3 {{ font-weight: 800 !important; font-size: 1.25rem !important; }}
p, li, label {{ font-size: 1.02rem; }}

/* brand bar */
.brand {{ display:flex; align-items:center; gap:.6rem; font-weight:900; font-size:1.5rem; color:{INK}; }}
.brand .dot {{ width:14px; height:14px; border-radius:50%; background:{WASTE}; border:2.5px solid {INK}; }}
.tag {{ display:inline-block; font-weight:800; font-size:.78rem; letter-spacing:.06em; text-transform:uppercase;
       padding:.25rem .6rem; border:2px solid {INK}; border-radius:999px; background:#fff3c4; color:{INK}; }}

/* nav: the segmented control becomes big bold tabs */
[data-testid="stButtonGroup"] [role="radiogroup"] {{ gap: .5rem; flex-wrap: wrap; }}
[data-testid="stButtonGroup"] button {{ border: 2.5px solid {INK} !important; border-radius: 12px !important;
       padding: .5rem 1.05rem !important; background: #fff !important; box-shadow: 3px 3px 0 {INK}; }}
[data-testid="stButtonGroup"] button p {{ font-weight: 800 !important; font-size: 1.02rem !important; color: {INK} !important; }}
[data-testid="stButtonGroup"] button[aria-checked="true"] {{ background: {INK} !important; box-shadow: 3px 3px 0 {WASTE}; }}
[data-testid="stButtonGroup"] button[aria-checked="true"] p {{ color: #fff !important; }}
[data-testid="stButtonGroup"] button:hover {{ transform: translate(-1px,-1px); }}

/* buttons */
.stButton > button p {{ font-weight: 800 !important; font-size: 1.02rem !important; }}
.stButton > button, .stDownloadButton > button, [data-testid="stFormSubmitButton"] > button {{
       font-weight: 800 !important; font-size: 1rem !important; border: 2.5px solid {INK} !important;
       border-radius: 12px !important; box-shadow: 3px 3px 0 {INK}; padding: .55rem 1.1rem !important; }}
.stButton > button:hover {{ transform: translate(-1px,-1px); box-shadow: 4px 4px 0 {INK}; }}
.stButton > button[kind="primary"] {{ background: {USEFUL} !important; color: #fff !important; }}
.stButton > button[kind="primary"] p {{ color: #fff !important; }}

/* cards */
.card {{ border: 2.5px solid {INK}; border-radius: 16px; background: #fff; padding: 1.1rem 1.25rem;
        box-shadow: 5px 5px 0 {INK}; margin-bottom: 1rem; }}
.kpi .label {{ font-weight: 800; font-size: .8rem; letter-spacing: .07em; text-transform: uppercase; color: {MUTED}; }}
.kpi .value {{ font-weight: 900; font-size: 2.5rem; line-height: 1.1; color: {INK}; margin-top: .2rem; }}
.kpi .sub {{ font-weight: 700; font-size: .95rem; color: {MUTED}; margin-top: .25rem; }}
.kpi.waste .value {{ color: {WASTE}; }}
.hero {{ font-weight: 900; font-size: 3.1rem; line-height: 1.05; color: {INK}; letter-spacing: -0.03em; margin: .4rem 0 .3rem; }}
.hero em {{ font-style: normal; color: {WASTE}; }}
.lead {{ font-weight: 600; font-size: 1.2rem; color: {MUTED}; margin-bottom: 1.2rem; }}
.fix {{ display:flex; gap:1rem; align-items:flex-start; }}
.fix .num {{ flex:0 0 auto; width:2.6rem; height:2.6rem; border-radius:12px; background:{WASTE}; color:#fff; border:2.5px solid {INK};
            font-weight:900; font-size:1.4rem; display:flex; align-items:center; justify-content:center; }}
.fix .title {{ font-weight: 850; font-size: 1.2rem; color: {INK}; }}
.fix .save {{ font-weight: 900; color: {WASTE}; white-space: nowrap; font-size: 1.15rem; }}
.fix .body {{ font-size: 1rem; color: {INK}; margin-top: .25rem; }}
.fix .how {{ font-weight: 700; margin-top: .35rem; }}
.verdict {{ font-weight: 900; font-size: 2rem; line-height: 1.15; padding: 1rem 1.25rem; border: 2.5px solid {INK};
           border-radius: 16px; box-shadow: 5px 5px 0 {INK}; margin: .5rem 0 1.2rem; }}
.verdict.bad {{ background: #ffe1d4; }} .verdict.good {{ background: #d9f2e4; }}
.verdict small {{ display:block; font-weight: 700; font-size: 1.05rem; margin-top: .35rem; color: {INK}; }}
.muted {{ color: {MUTED}; font-weight: 600; }}
[data-testid="stExpander"] summary p {{ font-weight: 800 !important; font-size: 1.05rem !important; }}
</style>
""",
    unsafe_allow_html=True,
)


# ---------- helpers ----------
def api(method: str, path: str, **kw):
    try:
        r = HTTP.request(method, f"{API}{path}", timeout=60, **kw)
    except requests.RequestException:
        st.error(f"**Can't reach the backend at {API}.** Start it in another window with:  `uvicorn app.main:app --port 8000`")
        st.stop()
    if r.status_code >= 400:
        st.error(f"**Backend error {r.status_code}:** {r.text[:300]}")
        st.stop()
    return r.json()


def get(path: str, **params):
    return api("GET", path, params={k: v for k, v in params.items() if v not in (None, "")})


def tok(n: float) -> str:
    n = float(n or 0)
    for size, unit in ((1e9, "B"), (1e6, "M"), (1e3, "k")):
        if abs(n) >= size:
            return f"{n / size:.1f}{unit}"
    return f"{n:.0f}"


def usd(x: float) -> str:
    return f"${x:,.2f}"


def esc(s) -> str:
    return html.escape(str(s))


def kpi(col, label: str, value: str, sub: str = "", waste: bool = False) -> None:
    col.markdown(
        f'<div class="card kpi{" waste" if waste else ""}"><div class="label">{esc(label)}</div>'
        f'<div class="value">{esc(value)}</div><div class="sub">{esc(sub) or "&nbsp;"}</div></div>',
        unsafe_allow_html=True,
    )


def fix_card(num: int | str, title: str, saving: str, body: str, how: str) -> None:
    st.markdown(
        f'<div class="card fix"><div class="num">{esc(num)}</div><div style="flex:1">'
        f'<div style="display:flex;justify-content:space-between;gap:1rem"><span class="title">{esc(title)}</span>'
        f'<span class="save">{esc(saving)}</span></div>'
        f'<div class="body">{esc(body)}</div><div class="how">→ {esc(how)}</div></div></div>',
        unsafe_allow_html=True,
    )


def style(fig: go.Figure, height: int = 340, legend: bool = True) -> go.Figure:
    fig.update_layout(
        height=height,
        margin=dict(l=10, r=10, t=10, b=10),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family=FONT, color=INK, size=14),
        showlegend=legend,
        legend=dict(orientation="h", y=1.12, x=0, title=None, traceorder="normal", font=dict(size=14)),
        hoverlabel=dict(bgcolor="white", font=dict(family=FONT, size=14)),
        bargap=0.25,
    )
    fig.update_xaxes(showgrid=False, linecolor=INK, tickcolor=INK, tickfont=dict(color=MUTED))
    fig.update_yaxes(gridcolor=GRID, zeroline=False, tickfont=dict(color=MUTED))
    return fig


def show(fig: go.Figure) -> None:
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


def go_to(page: str) -> None:
    st.session_state.page = st.session_state.last_page = page


def keep_selected(key: str, fallback: str) -> None:
    """Clicking the active tab again would unselect it; keep it selected instead."""
    last = f"last_{key}"
    if st.session_state.get(key) is None:
        st.session_state[key] = st.session_state.get(last, fallback)
    else:
        st.session_state[last] = st.session_state[key]


def seed_demo() -> None:
    api("POST", "/demo/seed")
    go_to("Overview")
    st.session_state.toast = "Demo data loaded."


# ---------- top bar ----------
if "page" not in st.session_state:
    st.session_state.page = "Overview"
if st.session_state.get("toast"):
    st.toast(st.session_state.pop("toast"))

top_l, top_r = st.columns([3, 2], vertical_alignment="center")
top_r.markdown('<div style="height:2px"></div>', unsafe_allow_html=True)
top_l.markdown('<div class="brand"><span class="dot"></span>LLM Token Auditor</div>', unsafe_allow_html=True)
with top_r:
    src_label = st.segmented_control(
        "Show", ["All data", "Real", "Demo"], default="All data", key="src", label_visibility="collapsed",
        on_change=keep_selected, args=("src", "All data"),
    ) or "All data"
SRC = {"All data": "all", "Real": "real", "Demo": "simulated"}[src_label]

page = st.segmented_control(
    "Page", PAGES, key="page", label_visibility="collapsed", on_change=keep_selected, args=("page", "Overview")
) or "Overview"

ov = get("/overview", source=SRC)

# ---------- empty state: two big buttons, nothing else ----------
if ov["sessions"] == 0 and page != "Add data":
    st.markdown('<div class="hero">Find the tokens<br>you didn\'t need to spend.</div>', unsafe_allow_html=True)
    msg = {
        "all": "No data yet. Load the demo team to look around, or add your own Claude Code logs.",
        "real": "No real data yet. Add your Claude Code logs, or switch the filter to All data.",
        "simulated": "No demo data loaded. Load it with one click.",
    }[SRC]
    st.markdown(f'<div class="lead">{msg}</div>', unsafe_allow_html=True)
    a, b, _ = st.columns([1, 1, 2])
    a.button("Load demo data", type="primary", use_container_width=True, on_click=seed_demo)
    b.button("Add my logs", use_container_width=True, on_click=go_to, args=("Add data",))
    st.stop()

if ov.get("has_simulated") and page != "Add data":
    st.markdown('<span class="tag">⚠ Demo data — six fictional developers, not a real company</span>', unsafe_allow_html=True)


# ======================= OVERVIEW =======================
if page == "Overview":
    st.markdown(
        f'<div class="hero"><em>{ov["waste_token_pct"]:.0f}%</em> of tokens were avoidable.</div>'
        f'<div class="lead">{tok(ov["waste_tokens"])} tokens and about {usd(ov["waste_cost"])} you didn\'t need to spend · '
        f'{ov["users"]} developers · {ov["sessions"]} sessions · {ov["first_day"]} → {ov["last_day"]}</div>',
        unsafe_allow_html=True,
    )
    c1, c2, c3, c4 = st.columns(4)
    kpi(c1, "Tokens used", tok(ov["total_tokens"]), f"{ov['turns']:,} model calls")
    kpi(c2, "Avoidable tokens", tok(ov["waste_tokens"]), f"{ov['waste_token_pct']}% of usage", waste=True)
    kpi(c3, "Spend (est.)", usd(ov["total_cost"]), "from the price table")
    kpi(c4, "Avoidable spend", usd(ov["waste_cost"]), f"{ov['waste_cost_pct']}% of spend", waste=True)

    if ov["by_rule"]:
        st.markdown("## Fix these first")
        for i, r in enumerate(ov["by_rule"][:3], 1):
            fix_card(i, r["title"], f"save {usd(r['cost_wasted'])}", f"{r['what']} Found in {r['sessions']} sessions.", r["fix"])
    else:
        st.success("**No waste detected in this data.**")

    left, right = st.columns([3, 2])
    with left:
        st.markdown("### Every day: useful vs avoidable")
        d = pd.DataFrame(get("/daily", source=SRC))
        d["useful"] = d["tokens"] - d["waste_tokens"]
        fig = go.Figure()
        fig.add_bar(x=d["date"], y=d["useful"], name="Useful", marker_color=USEFUL,
                    marker_line=dict(color=PAPER, width=1), hovertemplate="%{x}<br>Useful: %{y:.3s}<extra></extra>")
        fig.add_bar(x=d["date"], y=d["waste_tokens"], name="Avoidable", marker_color=WASTE,
                    marker_line=dict(color=PAPER, width=1), hovertemplate="%{x}<br>Avoidable: %{y:.3s}<extra></extra>")
        fig.update_layout(barmode="stack")
        fig.update_yaxes(title="tokens")
        show(style(fig))
    with right:
        st.markdown("### Where the waste comes from")
        if ov["by_rule"]:
            r = pd.DataFrame(ov["by_rule"]).sort_values("cost_wasted")
            fig = go.Figure(go.Bar(
                x=r["cost_wasted"], y=r["title"], orientation="h", marker_color=WASTE,
                text=[usd(v) for v in r["cost_wasted"]], textposition="outside", cliponaxis=False,
                textfont=dict(size=14, color=INK),
                customdata=r[["sessions", "tokens_wasted"]],
                hovertemplate="%{y}<br>$%{x:.2f} avoidable<br>%{customdata[0]} sessions · %{customdata[1]:.3s} tokens<extra></extra>",
            ))
            fig.update_xaxes(title="USD (est.)", showgrid=True, gridcolor=GRID, range=[0, float(r["cost_wasted"].max()) * 1.3])
            fig.update_yaxes(showgrid=False)
            show(style(fig, legend=False))

    if ov["by_rule"]:
        with st.expander("See every finding"):
            rules = get("/rules")["rules"]
            titles = {r["rule"]: r["title"] for r in rules}
            users = [u["user"] for u in get("/users", source=SRC)]
            f1, f2 = st.columns(2)
            rule = f1.selectbox("Cause", ["All"] + list(titles), format_func=lambda k: "All causes" if k == "All" else titles[k])
            user = f2.selectbox("Developer", ["All"] + users)
            rows = get("/findings", source=SRC, rule=None if rule == "All" else rule,
                       user=None if user == "All" else user, limit=500)
            if rows:
                df = pd.DataFrame(rows)
                st.markdown(f"**{len(df)} findings · {tok(df['tokens_wasted'].sum())} tokens · {usd(df['cost_wasted'].sum())}**")
                t = df[["started_at", "user", "project", "title", "tokens_wasted", "cost_wasted", "evidence", "fix"]].copy()
                t["started_at"] = pd.to_datetime(t["started_at"], format="ISO8601").dt.strftime("%d %b %H:%M")
                st.dataframe(t, use_container_width=True, hide_index=True, height=420, column_config={
                    "started_at": "When", "user": "Developer", "project": "Project", "title": "Cause",
                    "tokens_wasted": st.column_config.NumberColumn("Avoidable tokens", format="%d"),
                    "cost_wasted": st.column_config.NumberColumn("Avoidable $", format="$%.2f"),
                    "evidence": st.column_config.TextColumn("Why", width="large"),
                    "fix": st.column_config.TextColumn("Fix", width="large"),
                })
            else:
                st.info("Nothing matches this filter.")
    st.caption("Waste figures are conservative rule-based estimates, not measurements. Costs use the price table in app/pricing.py.")


# ======================= SESSIONS =======================
elif page == "Sessions":
    st.markdown("# One session, message by message")
    sessions = get("/sessions", source=SRC, sort="waste", limit=300)
    labels = {
        s["id"]: f"{s['user']} · {s['project']} · {s['started_at'][:10]} · {s['turns']} messages · {usd(s['waste_cost'])} avoidable"
        for s in sessions
    }
    sid = st.selectbox("Pick a session (most wasteful first)", list(labels), format_func=labels.get)
    s = get(f"/sessions/{sid}")
    c1, c2, c3, c4 = st.columns(4)
    kpi(c1, "Messages", f"{s['turns']}", f"{s['minutes']:.0f} minutes")
    kpi(c2, "Tokens used", tok(s["total_tokens"]), f"peak context {tok(s['peak_context'])}")
    kpi(c3, "Avoidable tokens", tok(s["waste_tokens"]), f"{s['waste_token_pct']}% of this session", waste=True)
    kpi(c4, "Avoidable spend", usd(s["waste_cost"]), s["model"], waste=True)

    st.markdown("### How big each message got")
    t = pd.DataFrame(s["turn_data"])
    thresholds = get("/rules")["thresholds"]
    fig = go.Figure()
    fig.add_scatter(x=t["turn"], y=t["context_tokens"], mode="lines", name="Tokens sent with each message",
                    line=dict(color=USEFUL, width=3), fill="tozeroy", fillcolor="rgba(42,120,214,0.12)",
                    customdata=t[["output_tokens", "tool_errors"]],
                    hovertemplate="Message %{x}<br>Sent: %{y:.3s} tokens<br>Reply: %{customdata[0]} tokens<br>Tool errors: %{customdata[1]}<extra></extra>")
    err = t[t["tool_errors"] > 0]
    if len(err):
        fig.add_scatter(x=err["turn"], y=err["context_tokens"], mode="markers", name="Tool call failed",
                        marker=dict(color=WASTE, size=11, symbol="x", line=dict(color=PAPER, width=1)),
                        hovertemplate="Message %{x}: tool call failed<extra></extra>")
    fig.add_hline(y=thresholds["LONG_CONTEXT_THRESHOLD"], line=dict(color=INK, dash="dot", width=1.5),
                  annotation_text="too-long line", annotation_position="top left", annotation_font=dict(color=INK, size=13))
    fig.update_xaxes(title="message number")
    fig.update_yaxes(title="tokens", rangemode="tozero")
    show(style(fig, height=380))

    st.markdown("### What went wrong")
    if s["findings"]:
        for i, f in enumerate(s["findings"], 1):
            fix_card(i, f["title"], f"save {usd(f['cost_wasted'])}", f["evidence"], f["fix"])
    else:
        st.success("**Clean session. Nothing to fix.**")


# ======================= TEAM =======================
elif page == "Team":
    st.markdown("# Who wastes the most, and why")
    st.markdown('<div class="lead">For coaching habits, not ranking people. Each person has one main thing to fix.</div>',
                unsafe_allow_html=True)
    u = pd.DataFrame(get("/users", source=SRC))
    top = u.sort_values("waste_cost", ascending=False)
    cols = st.columns(min(3, len(top)))
    for col, (_, row) in zip(cols, top.head(3).iterrows(), strict=False):
        kpi(col, row["user"], f"{row['waste_token_pct']:.0f}% avoidable", f"Main issue: {row['top_issue']}", waste=True)

    u["useful"] = u["tokens"] - u["waste_tokens"]
    u = u.sort_values("tokens", ascending=True)
    fig = go.Figure()
    fig.add_bar(y=u["user"], x=u["useful"], orientation="h", name="Useful", marker_color=USEFUL,
                marker_line=dict(color=PAPER, width=1), hovertemplate="%{y}<br>Useful: %{x:.3s}<extra></extra>")
    fig.add_bar(y=u["user"], x=u["waste_tokens"], orientation="h", name="Avoidable", marker_color=WASTE,
                marker_line=dict(color=PAPER, width=1), text=[f"{p:.0f}%" for p in u["waste_token_pct"]],
                textposition="outside", cliponaxis=False, textfont=dict(size=14, color=INK),
                hovertemplate="%{y}<br>Avoidable: %{x:.3s}<extra></extra>")
    fig.update_layout(barmode="stack")
    fig.update_xaxes(title="tokens", showgrid=True, gridcolor=GRID, range=[0, float(u["tokens"].max()) * 1.12])
    fig.update_yaxes(showgrid=False, tickfont=dict(size=15, color=INK))
    show(style(fig, height=max(260, 55 * len(u))))
    tbl = top[["user", "sessions", "tokens", "waste_token_pct", "waste_cost", "top_issue"]]
    st.dataframe(tbl, use_container_width=True, hide_index=True, column_config={
        "user": "Developer", "sessions": "Sessions",
        "tokens": st.column_config.NumberColumn("Tokens", format="%d"),
        "waste_token_pct": st.column_config.ProgressColumn("Avoidable", format="%.0f%%", min_value=0, max_value=100),
        "waste_cost": st.column_config.NumberColumn("Avoidable $", format="$%.2f"),
        "top_issue": "Main issue",
    })


# ======================= FORECAST =======================
elif page == "Forecast":
    st.markdown("# Will we run out this month?")
    default = get("/forecast", source=SRC)
    budget_m = st.number_input("Monthly team budget (million tokens)", min_value=1,
                               value=int(default["budget_tokens"] / 1e6), step=10)
    f = get("/forecast", source=SRC, budget=int(budget_m * 1e6))
    if f["budget_hit_date"]:
        after = (f"With the fixes it lasts until {f['budget_hit_date_with_fixes']}." if f["budget_hit_date_with_fixes"]
                 else "With the fixes you stay under budget.")
        when = pd.to_datetime(f["budget_hit_date"], format="ISO8601").strftime("%d %b")
        st.markdown(f'<div class="verdict bad">⚠ Budget runs out on {when}.<small>{esc(after)}</small></div>',
                    unsafe_allow_html=True)
    else:
        st.markdown('<div class="verdict good">✓ On track to stay under budget.<small>Keep it that way.</small></div>',
                    unsafe_allow_html=True)
    c1, c2, c3 = st.columns(3)
    kpi(c1, f"Used so far · {f['month']}", tok(f["month_to_date_tokens"]), f"day {f['day_of_month']} of {f['days_in_month']}")
    kpi(c2, "Month-end, as is", tok(f["projected_tokens"]), f"{f['projected_pct_of_budget']:.0f}% of budget", waste=True)
    kpi(c3, "Month-end, with fixes", tok(f["projected_tokens_with_fixes"]), f"{f['projected_with_fixes_pct_of_budget']:.0f}% of budget")

    bars = pd.DataFrame({
        "label": ["Used so far", "Month-end, as is", "Month-end, with fixes"],
        "value": [f["month_to_date_tokens"], f["projected_tokens"], f["projected_tokens_with_fixes"]],
        "color": [MUTED, WASTE, USEFUL],
    })
    fig = go.Figure(go.Bar(x=bars["value"], y=bars["label"], orientation="h", marker_color=bars["color"],
                           text=[tok(v) for v in bars["value"]], textposition="outside", cliponaxis=False,
                           textfont=dict(size=15, color=INK), hovertemplate="%{y}: %{x:.3s} tokens<extra></extra>"))
    fig.add_vline(x=f["budget_tokens"], line=dict(color=INK, dash="dash", width=2),
                  annotation_text=f"budget {tok(f['budget_tokens'])}", annotation_position="top",
                  annotation_font=dict(size=14, color=INK))
    fig.update_yaxes(autorange="reversed", showgrid=False, tickfont=dict(size=15, color=INK))
    fig.update_xaxes(title="tokens", showgrid=True, gridcolor=GRID,
                     range=[0, max(float(bars["value"].max()), f["budget_tokens"]) * 1.15])
    style(fig, height=280, legend=False)
    fig.update_layout(margin=dict(l=10, r=10, t=34, b=10))
    show(fig)
    st.caption(f"Straight-line estimate from the last 7 days ({tok(f['daily_rate_tokens'])}/day). "
               f"'With fixes' removes the {f['waste_share_pct']}% of recent usage flagged as avoidable.")


# ======================= CHECK RULES =======================
elif page == "Check rules":
    st.markdown("# Is the tool right?")
    st.markdown('<div class="lead">Look at each flagged session and say if it was real waste. '
                'That gives you an honest accuracy number for every rule.</div>', unsafe_allow_html=True)
    v = get("/validation", source=SRC)
    c1, c2, c3 = st.columns(3)
    kpi(c1, "Reviewed", f"{v['labeled']}", "findings checked by you")
    kpi(c2, "Real waste", f"{v['confirmed']}", "confirmed")
    kpi(c3, "Accuracy", "—" if v["precision_pct"] is None else f"{v['precision_pct']:.0f}%", "share confirmed as real")

    pending = [q for q in v["queue"] if q["label"] is None]
    if not v["queue"]:
        st.info("**No findings to review in this data.**")
    elif not pending:
        st.success("**All done. Everything has been reviewed.**")
    else:
        # Take turns across rules so every rule gets reviewed, not only the most common one.
        groups: dict[str, list] = {}
        for q in pending:
            groups.setdefault(q["rule"], []).append(q)
        batch = []
        while len(batch) < 5 and any(groups.values()):
            for g in groups.values():
                if g and len(batch) < 5:
                    batch.append(g.pop(0))
        st.markdown(f"## Review ({len(pending)} left)")
        for q in batch:
            key = f"{q['session_id']}-{q['rule']}"
            with st.container(border=True):
                a, b, c = st.columns([5, 1.2, 1.2], vertical_alignment="center")
                a.markdown(f"**{q['title']}** · {q['user']} · {q['project']} · {q['started_at'][:10]}  \n{q['evidence']}  \n"
                           f"<span class='muted'>Claims {tok(q['tokens_wasted'])} tokens / {usd(q['cost_wasted'])} avoidable</span>",
                           unsafe_allow_html=True)
                if b.button("✅ Waste", key=f"y-{key}", use_container_width=True, type="primary"):
                    api("POST", "/labels", json={"session_id": q["session_id"], "rule": q["rule"], "is_waste": True})
                    st.rerun()
                if c.button("❌ Not waste", key=f"n-{key}", use_container_width=True):
                    api("POST", "/labels", json={"session_id": q["session_id"], "rule": q["rule"], "is_waste": False})
                    st.rerun()

    if v["by_rule"] and v["labeled"]:
        st.markdown("### Accuracy by rule")
        br = pd.DataFrame(v["by_rule"])[["title", "findings", "labeled", "confirmed", "precision_pct"]]
        br["precision_pct"] = [("not reviewed" if pd.isna(p) else f"{p:.0f}%") for p in br["precision_pct"]]
        st.dataframe(br, use_container_width=True, hide_index=True, column_config={
            "title": "Rule", "findings": "Found", "labeled": "Reviewed", "confirmed": "Real waste", "precision_pct": "Accuracy"})
        if st.button("Reset my reviews"):
            api("DELETE", "/labels")
            st.rerun()


# ======================= ADD DATA =======================
elif page == "Add data":
    st.markdown("# Add data")
    left, right = st.columns(2, gap="large")
    with left, st.container(border=True):
        st.markdown("## Your Claude Code logs")
        st.markdown("Find them in `C:\\Users\\<you>\\.claude\\projects\\`. Drop the `.jsonl` files below.")
        user = st.text_input("Whose usage is this?", value="me")
        files = st.file_uploader("Session logs", type=["jsonl"], accept_multiple_files=True, label_visibility="collapsed")
        if st.button("Import logs", type="primary", use_container_width=True, disabled=not files):
            res = api("POST", "/import/claude-code", data={"user": user},
                      files=[("files", (f.name, f.getvalue(), "application/octet-stream")) for f in files])
            st.success(f"**Imported {res['sessions_new']} new and {res['sessions_replaced']} updated sessions** "
                       f"({res['turns']} model calls).")
            if res["empty_files"]:
                st.warning(f"{res['empty_files']} file(s) had no usable data.")
        st.caption("Only token counts, model names, tool names and hashed file paths are kept. Your prompts are never stored.")
    with right, st.container(border=True):
        st.markdown("## Demo team")
        st.markdown("Six fictional developers, each with one bad habit, over the last 21 days. Labelled as demo everywhere.")
        st.button("Load demo data", type="primary", use_container_width=True, on_click=seed_demo)
        if st.button("Remove demo data", use_container_width=True):
            st.toast(f"Removed {api('DELETE', '/demo')['removed']} demo sessions.")

    with st.expander("Danger zone"):
        if st.button("Delete all my imported sessions"):
            st.toast(f"Removed {api('DELETE', '/sessions')['removed']} sessions.")
