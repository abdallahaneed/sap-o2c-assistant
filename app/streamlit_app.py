"""Streamlit frontend: a chat page and a KPI dashboard. All data comes from the FastAPI backend.

Start the backend first:  uv run uvicorn o2c.api:app
Then this app:            uv run streamlit run app/streamlit_app.py
"""

from __future__ import annotations

import json

import altair as alt
import pandas as pd
import streamlit as st

from o2c import ui

BLUE = "#2a78d6"  # one series, one color: slot 1 of a colorblind-checked palette

st.set_page_config(page_title="SAP O2C Assistant", page_icon="📦", layout="wide")


@st.cache_data(ttl=60, show_spinner=False)
def load_kpis() -> dict:
    return ui.get_json("/kpis")


@st.cache_data(ttl=30, show_spinner=False)
def load_health() -> dict:
    return ui.get_json("/health")


# Sidebar: language, page, data refresh

with st.sidebar:
    lang_label = st.radio("Sprache / Language", ["Deutsch", "English"], horizontal=True)
    lang = "de" if lang_label == "Deutsch" else "en"
    t = ui.TEXT[lang]
    page = st.radio(" ", [t["page_chat"], t["page_dashboard"]], label_visibility="collapsed")
    st.divider()
    if st.button(t["refresh"], width="stretch"):
        try:
            ui.post_json("/refresh")
            st.cache_data.clear()
            st.success(t["refreshed"])
        except ui.ApiError as err:
            st.error(str(err))

st.title(t["title"])
st.caption(t["subtitle"])

try:
    kpis = load_kpis()
except ui.ApiError as err:
    st.error(str(err))
    st.stop()

sync = kpis.get("last_sync") or {}
source = t["source_api"] if sync.get("source") == "api" else t["source_fixtures"]
st.caption(f"{t['data_from']}: {ui.fmt_time(sync.get('run_time'), lang)} · {source}")


def show_tool_calls(calls: list[dict]) -> None:
    """The expandable section that shows which tools the model used, with inputs and results."""
    if not calls:
        return
    with st.expander(f"{t['tools_used']} ({len(calls)})"):
        for call in calls:
            marker = "⚠️ " if call.get("is_error") else ""
            st.markdown(f"{marker}**{call['name']}**")
            st.code(json.dumps(call.get("input", {}), ensure_ascii=False), language="json")
            output = json.dumps(call.get("output"), ensure_ascii=False, indent=1, default=str)
            st.code(output[:3000] + ("\n..." if len(output) > 3000 else ""), language="json")


def ask(question: str) -> None:
    """Send a question with the last turns as history and store the answer."""
    history = [
        {"role": m["role"], "content": m["content"]} for m in st.session_state.messages[-10:]
    ]
    st.session_state.messages.append({"role": "user", "content": question})
    try:
        with st.spinner(t["thinking"]):
            reply = ui.post_json(
                "/chat", {"question": question, "history": history}, timeout=ui.CHAT_TIMEOUT
            )
        st.session_state.messages.append(
            {"role": "assistant", "content": reply["answer"], "tool_calls": reply["tool_calls"]}
        )
    except ui.ApiError as err:
        st.session_state.messages.append({"role": "assistant", "content": f"⚠️ {err}"})


# Chat page

if page == t["page_chat"]:
    if "messages" not in st.session_state:
        st.session_state.messages = []

    try:
        if not load_health().get("chat_enabled"):
            st.warning(t["chat_off"])
    except ui.ApiError:
        pass  # the KPI call above already showed the connection problem

    if not st.session_state.messages:
        st.markdown(f"**{t['examples']}**")
        cols = st.columns(2)
        for i, example in enumerate(ui.EXAMPLE_QUESTIONS[lang]):
            if cols[i % 2].button(example, key=f"ex{i}", width="stretch"):
                ask(example)
                st.rerun()

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            show_tool_calls(message.get("tool_calls", []))

    if question := st.chat_input(t["chat_placeholder"]):
        ask(question)
        st.rerun()

    if st.session_state.messages and st.sidebar.button(t["clear_chat"]):
        st.session_state.messages = []
        st.rerun()


# Dashboard page

else:
    # Two tiles: the count is the headline, the value sits below it. Money needs the width.
    left_tile, right_tile = st.columns(2)
    for tile, count_key, value_key, data in [
        (left_tile, "kpi_open_orders", "kpi_open_value", kpis["open_orders"]),
        (right_tile, "kpi_dnb", "kpi_dnb_value", kpis["delivered_not_billed"]),
    ]:
        with tile.container(border=True):
            st.metric(t[count_key], data["count"])
            st.markdown(f"{t[value_key]}: **{ui.fmt_money(data['value'], lang)}**")

    st.subheader(t["chart_revenue"])
    revenue = pd.DataFrame(kpis["revenue_by_month"])
    if not revenue.empty:
        revenue["revenue"] = revenue["revenue"].astype(float)
        chart = (
            alt.Chart(revenue)
            .mark_bar(color=BLUE, cornerRadiusEnd=4)
            .encode(
                x=alt.X("month:N", title=t["col_month"], axis=alt.Axis(labelAngle=0)),
                y=alt.Y("revenue:Q", title=f"{t['col_revenue']} (USD)"),
                tooltip=[
                    alt.Tooltip("month:N", title=t["col_month"]),
                    alt.Tooltip("revenue:Q", title=t["col_revenue"], format=",.2f"),
                ],
            )
            .properties(height=280)
        )
        st.altair_chart(chart, width="stretch")
    st.caption(t["revenue_note"])

    left, right = st.columns(2)

    with left:
        st.subheader(t["chart_top"])
        top = pd.DataFrame(kpis["top_customers"])
        if not top.empty:
            top["revenue"] = top["revenue"].astype(float)
            chart = (
                alt.Chart(top)
                .mark_bar(color=BLUE, cornerRadiusEnd=4)
                .encode(
                    # long names share a prefix: give the labels room instead of cutting them
                    y=alt.Y(
                        "customer_name:N", sort="-x", title=None, axis=alt.Axis(labelLimit=260)
                    ),
                    x=alt.X("revenue:Q", title=f"{t['col_revenue']} (USD)"),
                    tooltip=[
                        alt.Tooltip("customer_name:N", title=t["col_customer"]),
                        alt.Tooltip("customer_id:N", title="ID"),
                        alt.Tooltip("revenue:Q", title=t["col_revenue"], format=",.2f"),
                    ],
                )
                .properties(height=240)
            )
            st.altair_chart(chart, width="stretch")

    with right:
        st.subheader(t["chart_funnel"])
        funnel = kpis["funnel"]
        steps = pd.DataFrame(
            [
                {"step": t["funnel_ordered"], "count": funnel["ordered"], "order": 1},
                {"step": t["funnel_delivered"], "count": funnel["delivered"], "order": 2},
                {"step": t["funnel_billed"], "count": funnel["billed"], "order": 3},
            ]
        )
        bars = (
            alt.Chart(steps)
            .mark_bar(color=BLUE, cornerRadiusEnd=4)
            .encode(
                y=alt.Y("step:N", sort=alt.SortField("order"), title=None),
                x=alt.X("count:Q", title=t["col_count"]),
                tooltip=[
                    alt.Tooltip("step:N", title=t["col_step"]),
                    alt.Tooltip("count:Q", title=t["col_count"]),
                ],
            )
        )
        labels = bars.mark_text(align="left", dx=6, color="gray").encode(text="count:Q")
        st.altair_chart((bars + labels).properties(height=240), width="stretch")

    st.subheader(t["table_dnb"])
    deliveries = kpis["delivered_not_billed"]["deliveries"]
    if deliveries:
        table = pd.DataFrame(
            [
                {
                    t["col_delivery"]: d["delivery_id"],
                    t["col_orders"]: ", ".join(d["order_ids"]),
                    t["col_customer"]: f"{d.get('customer_name') or ''} ({d['customer_id']})",
                    t["col_gi_date"]: d.get("goods_issue_date") or "-",
                    t["col_value"]: ui.fmt_money(d["value"], lang),
                }
                for d in deliveries
            ]
        )
        st.dataframe(table, hide_index=True, width="stretch")
