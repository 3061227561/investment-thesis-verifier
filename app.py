"""投资命题多证据验证器（Streamlit 版）。

运行：streamlit run app.py
"""

import os

import streamlit as st

from fetch_data import (
    API_KEY_ENV_VAR,
    TARGET_INDICATORS,
    fetch_indicators,
    find_indicator_values,
    load_api_key,
)

st.set_page_config(page_title="投资命题多证据验证器", page_icon="🧭", layout="wide")

# 预设命题 -> 取数参数
PROPOSITIONS = {
    "贵州茅台盈利改善来自主营业务": {
        "thscode": "600519.SH",
        "report": "2024-4",
        "company": "贵州茅台",
    },
}


def above(threshold):
    """生成「大于阈值即支持」的判定函数；取不到数值时返回 None。"""
    def check(value):
        if value is None:
            return None
        try:
            return float(value) > threshold
        except (TypeError, ValueError):
            return None

    return check


# 三个子问题：问题、对应指标、判定规则、支持/反对的阈值描述
SUB_QUESTIONS = [
    {
        "no": "子问题一",
        "question": "主营业务是否增长？",
        "metric": TARGET_INDICATORS[0],
        "rule": "营收同比增速 > 0",
        "check": above(0),
    },
    {
        "no": "子问题二",
        "question": "产品竞争力是否维持？",
        "metric": TARGET_INDICATORS[1],
        "rule": "销售毛利率 > 80%",
        "check": above(80),
    },
    {
        "no": "子问题三",
        "question": "利润是否有现金支撑？",
        "metric": TARGET_INDICATORS[2],
        "rule": "净利润现金含量 > 100%",
        "check": above(100),
    },
]


def bridge_secrets_to_env():
    """Streamlit Cloud 的 Secrets 不会自动变成环境变量，这里手动桥接。

    本地没有 .streamlit/secrets.toml 时访问 st.secrets 会报错，忽略即可。
    """
    try:
        secret = st.secrets[API_KEY_ENV_VAR]
    except Exception:
        return
    if isinstance(secret, str) and secret.strip():
        os.environ[API_KEY_ENV_VAR] = secret.strip()


@st.cache_data(ttl=300, show_spinner=False)
def get_indicator_values(thscode, report):
    """取数并提取指标；失败时 RuntimeError 会原样抛给调用方。"""
    api_key = load_api_key()
    payload = fetch_indicators(api_key, thscode=thscode, report=report)
    return find_indicator_values(payload, set(TARGET_INDICATORS))


def fmt(value):
    """把接口返回的数值格式化成百分比展示。"""
    try:
        return f"{float(value):.2f}%"
    except (TypeError, ValueError):
        return str(value)


def run_validation(proposition):
    params = PROPOSITIONS[proposition]
    bridge_secrets_to_env()
    try:
        values = get_indicator_values(params["thscode"], params["report"])
    except Exception as e:  # 网络、鉴权、解析等任何失败都落到这里
        return {"proposition": proposition, "params": params, "values": None, "error": str(e)}
    return {"proposition": proposition, "params": params, "values": values, "error": None}


def render_card(column, sub, value):
    with column.container(border=True):
        st.markdown(f"#### {sub['no']}")
        st.markdown(f"**{sub['question']}**")
        st.caption(f"指标：`{sub['metric']}`　判定规则：{sub['rule']}")

        if value is None:
            st.warning("⚠️ **无法验证**\n\n数据缺失")
            return None

        st.metric(label="当前值", value=fmt(value))
        result = sub["check"](value)
        if result:
            st.success("✅ **支持**")
        else:
            st.error("❌ **反对**")
        return result


st.title("🧭 投资命题多证据验证器")
st.caption("把一个投资命题拆成可验证的子问题，用财务数据逐条检验。")

with st.sidebar:
    st.header("验证设置")
    proposition = st.selectbox("选择要验证的命题", list(PROPOSITIONS.keys()))

    params = PROPOSITIONS[proposition]
    st.caption(f"标的：{params['company']}（{params['thscode']}）　报告期：{params['report']}")

    start = st.button("开始验证", type="primary", use_container_width=True)
    if st.button("刷新数据（清除缓存）", use_container_width=True):
        get_indicator_values.clear()
        st.session_state.pop("validation", None)
        st.rerun()

if start:
    with st.spinner("正在获取并验证财务数据…"):
        st.session_state["validation"] = run_validation(proposition)

validation = st.session_state.get("validation")

if validation is None:
    st.info("请在左侧选择命题后点击「开始验证」。")
    st.stop()

st.subheader(f"命题：{validation['proposition']}")

if validation["error"] is not None:
    st.error(f"数据获取失败，无法完成验证：{validation['error']}")
    st.stop()

values = validation["values"] or {}

cols = st.columns(3)
verdicts = [render_card(col, sub, values.get(sub["metric"])) for col, sub in zip(cols, SUB_QUESTIONS)]

# ---- 底部结论区 ----
st.divider()
with st.container(border=True):
    st.markdown("### 📌 结论")

    if any(v is False for v in verdicts):
        st.error("**当前证据不支持该命题：存在被逐条反驳的子证据。**")
    elif any(v is None for v in verdicts):
        st.warning("**当前证据不完整：部分子证据缺失，暂无法得出确定结论。**")
    else:
        st.success("**当前证据支持该命题。**")

    st.markdown("**推翻条件**")
    st.markdown(
        "- 若 **营收增速转负**（`operating_income_yoy_growth_ratio` ≤ 0）；\n"
        "- 若 **毛利率跌破 80%**（`sale_gross_margin` ≤ 80）；\n"
        "- 若 **净利润现金含量低于 100%**（`net_profit_cash_content` ≤ 100）；\n\n"
        "以上任一条件成立，此结论需要重新审视。"
    )

with st.expander("查看原始指标数据"):
    if values:
        st.json(values)
    else:
        st.write("本次未取到任何指标数据。")
