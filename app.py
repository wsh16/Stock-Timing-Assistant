from __future__ import annotations

import json
from typing import Any

import pandas as pd
import streamlit as st

from timing_assistant.a_share_lookup import lookup_a_share_match
from timing_assistant.config import ensure_runtime_dirs
from timing_assistant.constants import (
    APP_NAME,
    DEFAULT_COOLDOWN_DAYS,
    DEFAULT_POLL_MINUTES,
    DEFAULT_WINDOW_DAYS,
    MARKET_LABELS,
    MODE_LABELS,
    STREAMLIT_URL,
)
from timing_assistant.database import (
    delete_watchlist,
    get_settings,
    initialize_database,
    list_alert_logs,
    list_system_logs,
    list_watchlists,
    save_watchlist,
    set_watchlist_enabled,
    update_settings,
)
from timing_assistant.models import WatchlistRule
from timing_assistant.symbols import get_default_benchmarks, normalize_market, normalize_symbol


ensure_runtime_dirs()
initialize_database()

st.set_page_config(page_title=APP_NAME, layout="wide")


def mode_label(value: str) -> str:
    return MODE_LABELS.get(value, value)


def market_label(value: str) -> str:
    return MARKET_LABELS.get(value, value)


def pretty_json(value: str) -> str:
    if not value:
        return ""
    try:
        return json.dumps(json.loads(value), ensure_ascii=False, indent=2)
    except (json.JSONDecodeError, TypeError):
        return str(value)


def default_rule_initial() -> dict[str, Any]:
    return {
        "market": "A",
        "symbol": "",
        "display_name": "",
        "benchmark_symbol": "sh000001",
        "benchmark_name": "上证指数",
        "monitor_mode": "intraday",
        "window_days": DEFAULT_WINDOW_DAYS,
        "poll_interval_minutes": DEFAULT_POLL_MINUTES,
        "cooldown_trading_days": DEFAULT_COOLDOWN_DAYS,
        "buy_benchmark_min_pct": 1.0,
        "buy_stock_max_pct": -0.5,
        "buy_divergence_min_pct": 2.0,
        "sell_benchmark_max_pct": -1.0,
        "sell_stock_min_pct": 0.5,
        "sell_divergence_min_pct": 2.0,
        "enabled": 1,
        "notes": "",
    }


def watchlist_to_initial(rule: WatchlistRule, *, clear_identity: bool = False) -> dict[str, Any]:
    initial = {
        "market": rule.market,
        "symbol": rule.symbol,
        "display_name": rule.display_name,
        "benchmark_symbol": rule.benchmark_symbol,
        "benchmark_name": rule.benchmark_name,
        "monitor_mode": rule.monitor_mode,
        "window_days": rule.window_days,
        "poll_interval_minutes": rule.poll_interval_minutes,
        "cooldown_trading_days": rule.cooldown_trading_days,
        "buy_benchmark_min_pct": rule.buy_benchmark_min_pct,
        "buy_stock_max_pct": rule.buy_stock_max_pct,
        "buy_divergence_min_pct": rule.buy_divergence_min_pct,
        "sell_benchmark_max_pct": rule.sell_benchmark_max_pct,
        "sell_stock_min_pct": rule.sell_stock_min_pct,
        "sell_divergence_min_pct": rule.sell_divergence_min_pct,
        "enabled": 1 if rule.enabled else 0,
        "notes": rule.notes,
    }
    if clear_identity:
        initial["symbol"] = ""
        initial["display_name"] = ""
    return initial


def seed_rule_form(prefix: str, initial: dict[str, Any]) -> None:
    form_fields = [
        "market",
        "symbol",
        "display_name",
        "monitor_mode",
        "window_days",
        "poll_interval_minutes",
        "cooldown_trading_days",
        "buy_benchmark_min_pct",
        "buy_stock_max_pct",
        "buy_divergence_min_pct",
        "sell_benchmark_max_pct",
        "sell_stock_min_pct",
        "sell_divergence_min_pct",
        "enabled",
        "notes",
    ]
    for field in form_fields:
        st.session_state[f"{prefix}_{field}"] = initial[field]

    benchmark_defaults = get_default_benchmarks(initial["market"])
    matching_default = next(
        (
            item["label"]
            for item in benchmark_defaults
            if item["symbol"] == initial["benchmark_symbol"]
        ),
        "自定义",
    )
    st.session_state[f"{prefix}_benchmark_choice"] = matching_default
    st.session_state[f"{prefix}_benchmark_symbol"] = initial["benchmark_symbol"]
    st.session_state[f"{prefix}_benchmark_name"] = initial["benchmark_name"]
    st.session_state[f"{prefix}_last_market"] = initial["market"]
    st.session_state[f"{prefix}_auto_name"] = ""


def queue_rule_form_seed(prefix: str, initial: dict[str, Any], *, notice: str = "") -> None:
    st.session_state[f"{prefix}_seed_payload"] = initial
    if notice:
        st.session_state[f"{prefix}_seed_notice"] = notice


def apply_queued_rule_form_seed(prefix: str) -> None:
    payload = st.session_state.pop(f"{prefix}_seed_payload", None)
    if payload is not None:
        seed_rule_form(prefix, payload)
    notice = st.session_state.pop(f"{prefix}_seed_notice", None)
    if notice:
        st.session_state[f"{prefix}_active_notice"] = notice


def apply_a_share_symbol_autofill(prefix: str, initial: dict[str, Any], market: str) -> tuple[str, str]:
    symbol_key = f"{prefix}_symbol"
    display_name_key = f"{prefix}_display_name"
    auto_name_key = f"{prefix}_auto_name"

    if symbol_key not in st.session_state:
        st.session_state[symbol_key] = initial["symbol"]
    if display_name_key not in st.session_state:
        st.session_state[display_name_key] = initial["display_name"]
    if auto_name_key not in st.session_state:
        st.session_state[auto_name_key] = ""

    if market != "A":
        return "", ""

    current_symbol = str(st.session_state.get(symbol_key, "")).strip()
    match = lookup_a_share_match(current_symbol)
    if match is None:
        return "", ""

    if current_symbol != match.normalized_symbol:
        st.session_state[symbol_key] = match.normalized_symbol

    current_name = str(st.session_state.get(display_name_key, "")).strip()
    auto_name = str(st.session_state.get(auto_name_key, "")).strip()
    if match.display_name and (not current_name or current_name == auto_name):
        st.session_state[display_name_key] = match.display_name
        st.session_state[auto_name_key] = match.display_name

    return match.normalized_symbol, match.display_name


def parse_rule_form(prefix: str, *, initial: dict[str, Any]) -> dict[str, Any]:
    benchmark_choice_key = f"{prefix}_benchmark_choice"
    benchmark_symbol_key = f"{prefix}_benchmark_symbol"
    benchmark_name_key = f"{prefix}_benchmark_name"
    last_market_key = f"{prefix}_last_market"

    market = normalize_market(
        st.selectbox(
            "市场",
            options=["A", "US"],
            format_func=market_label,
            index=["A", "US"].index(initial["market"]),
            key=f"{prefix}_market",
        )
    )

    matched_symbol, matched_name = apply_a_share_symbol_autofill(prefix, initial, market)

    symbol_input = st.text_input(
        "股票代码",
        help="A股示例: 600519 或 000001.SZ；美股示例: AAPL",
        key=f"{prefix}_symbol",
    )
    display_name = st.text_input(
        "股票名称",
        help="可选，不填时默认使用代码。",
        key=f"{prefix}_display_name",
    )
    if market == "A":
        if matched_symbol and matched_name:
            st.caption(f"自动匹配：{matched_name} ({matched_symbol})")
        elif matched_symbol:
            st.caption(f"自动匹配完整代码：{matched_symbol}")
        else:
            st.caption("输入 6 位 A 股代码后会自动补全 `sh/sz` 前缀，并尝试带出股票名称。")

    benchmark_defaults = get_default_benchmarks(market)
    benchmark_labels = [item["label"] for item in benchmark_defaults]
    matching_default = next(
        (
            item["label"]
            for item in benchmark_defaults
            if item["symbol"] == initial["benchmark_symbol"]
        ),
        None,
    )
    market_changed = st.session_state.get(last_market_key, initial["market"]) != market
    if benchmark_choice_key not in st.session_state:
        st.session_state[benchmark_choice_key] = matching_default or "自定义"
    if benchmark_symbol_key not in st.session_state:
        st.session_state[benchmark_symbol_key] = initial["benchmark_symbol"]
    if benchmark_name_key not in st.session_state:
        st.session_state[benchmark_name_key] = initial["benchmark_name"]
    if market_changed:
        default_benchmark = benchmark_defaults[0]
        st.session_state[benchmark_choice_key] = default_benchmark["label"]
        st.session_state[benchmark_symbol_key] = default_benchmark["symbol"]
        st.session_state[benchmark_name_key] = default_benchmark["label"]
    st.session_state[last_market_key] = market

    benchmark_choice_options = benchmark_labels + ["自定义"]
    benchmark_choice = st.selectbox(
        "比较基准",
        options=benchmark_choice_options,
        index=benchmark_choice_options.index(
            st.session_state.get(benchmark_choice_key, matching_default or "自定义")
        ),
        key=f"{prefix}_benchmark_choice",
    )
    if benchmark_choice == "自定义":
        benchmark_symbol = st.text_input(
            "基准代码",
            value=st.session_state.get(benchmark_symbol_key, initial["benchmark_symbol"]),
            key=f"{prefix}_benchmark_symbol",
        )
        benchmark_name = st.text_input(
            "基准名称",
            value=st.session_state.get(benchmark_name_key, initial["benchmark_name"]),
            key=f"{prefix}_benchmark_name",
        )
        st.caption("美股示例：SPY、QQQ、DIA、IWM；A股示例：sh000001、sh000300、sz399006")
    else:
        picked = next(item for item in benchmark_defaults if item["label"] == benchmark_choice)
        st.session_state[benchmark_symbol_key] = picked["symbol"]
        st.session_state[benchmark_name_key] = picked["label"]
        benchmark_symbol = picked["symbol"]
        benchmark_name = picked["label"]
        st.caption(f"已选择默认基准：{benchmark_name} ({benchmark_symbol})")

    monitor_mode = st.radio(
        "监控模式",
        options=["intraday", "cross_day"],
        horizontal=True,
        format_func=mode_label,
        index=["intraday", "cross_day"].index(initial["monitor_mode"]),
        key=f"{prefix}_monitor_mode",
    )

    rule_col1, rule_col2, rule_col3 = st.columns(3)
    with rule_col1:
        window_days = st.selectbox(
            "跨日窗口天数",
            options=[3, 5, 10, 20],
            index=[3, 5, 10, 20].index(int(initial["window_days"])),
            disabled=monitor_mode != "cross_day",
            key=f"{prefix}_window_days",
        )
    with rule_col2:
        poll_interval_minutes = st.selectbox(
            "轮询间隔(分钟)",
            options=[5, 15, 30, 60],
            index=[5, 15, 30, 60].index(int(initial["poll_interval_minutes"])),
            key=f"{prefix}_poll_interval_minutes",
        )
    with rule_col3:
        cooldown_trading_days = st.number_input(
            "冷却交易日",
            min_value=0,
            max_value=20,
            value=int(initial["cooldown_trading_days"]),
            step=1,
            key=f"{prefix}_cooldown_trading_days",
        )

    st.markdown("**买入阈值**")
    buy_col1, buy_col2, buy_col3 = st.columns(3)
    with buy_col1:
        buy_benchmark_min_pct = st.number_input(
            "基准涨跌幅下限(%)",
            value=float(initial["buy_benchmark_min_pct"]),
            step=0.1,
            key=f"{prefix}_buy_benchmark_min_pct",
        )
    with buy_col2:
        buy_stock_max_pct = st.number_input(
            "个股涨跌幅上限(%)",
            value=float(initial["buy_stock_max_pct"]),
            step=0.1,
            key=f"{prefix}_buy_stock_max_pct",
        )
    with buy_col3:
        buy_divergence_min_pct = st.number_input(
            "背离差下限(%)",
            value=float(initial["buy_divergence_min_pct"]),
            step=0.1,
            key=f"{prefix}_buy_divergence_min_pct",
        )
    st.caption(
        "说明：买入规则使用“基准涨跌幅 - 个股涨跌幅”计算背离。"
        "例如填 `1 / 0 / 3`，表示只有当基准至少涨 1%、个股最多持平，且基准至少强于个股 3% 时才提醒；"
        "如果允许个股上涨，可把“个股涨跌幅上限”设成正数，例如 `1` 表示个股最多涨 1%。"
    )

    st.markdown("**卖出阈值**")
    sell_col1, sell_col2, sell_col3 = st.columns(3)
    with sell_col1:
        sell_benchmark_max_pct = st.number_input(
            "基准涨跌幅上限(%)",
            value=float(initial["sell_benchmark_max_pct"]),
            step=0.1,
            key=f"{prefix}_sell_benchmark_max_pct",
        )
    with sell_col2:
        sell_stock_min_pct = st.number_input(
            "个股涨跌幅下限(%)",
            value=float(initial["sell_stock_min_pct"]),
            step=0.1,
            key=f"{prefix}_sell_stock_min_pct",
        )
    with sell_col3:
        sell_divergence_min_pct = st.number_input(
            "背离差下限(%)",
            value=float(initial["sell_divergence_min_pct"]),
            step=0.1,
            key=f"{prefix}_sell_divergence_min_pct",
        )
    st.caption(
        "说明：卖出规则使用“个股涨跌幅 - 基准涨跌幅”计算背离。"
        "例如填 `-1 / 0 / 3`，表示只有当基准至少跌 1%、个股至少持平，且个股至少强于基准 3% 时才提醒；"
        "如果想要求个股必须上涨 1% 以上，可把“个股涨跌幅下限”设成 `1`。"
    )

    notes = st.text_area(
        "备注",
        value=initial["notes"],
        key=f"{prefix}_notes",
    )
    enabled = st.checkbox(
        "启用这条规则",
        value=bool(initial["enabled"]),
        key=f"{prefix}_enabled",
    )

    return {
        "market": market,
        "symbol": symbol_input.strip(),
        "display_name": display_name.strip(),
        "benchmark_symbol": benchmark_symbol.strip(),
        "benchmark_name": benchmark_name.strip(),
        "monitor_mode": monitor_mode,
        "window_days": int(window_days),
        "poll_interval_minutes": int(poll_interval_minutes),
        "cooldown_trading_days": int(cooldown_trading_days),
        "buy_benchmark_min_pct": float(buy_benchmark_min_pct),
        "buy_stock_max_pct": float(buy_stock_max_pct),
        "buy_divergence_min_pct": float(buy_divergence_min_pct),
        "sell_benchmark_max_pct": float(sell_benchmark_max_pct),
        "sell_stock_min_pct": float(sell_stock_min_pct),
        "sell_divergence_min_pct": float(sell_divergence_min_pct),
        "enabled": 1 if enabled else 0,
        "notes": notes.strip(),
    }


def normalize_rule_payload(raw: dict[str, Any]) -> dict[str, Any]:
    market = normalize_market(raw["market"])
    symbol = normalize_symbol(market, raw["symbol"])
    benchmark_symbol = normalize_symbol(market, raw["benchmark_symbol"], is_benchmark=True)
    return {
        **raw,
        "market": market,
        "symbol": symbol,
        "display_name": raw["display_name"] or raw["symbol"].upper(),
        "benchmark_symbol": benchmark_symbol,
        "benchmark_name": raw["benchmark_name"] or raw["benchmark_symbol"].upper(),
    }


def render_watchlists_page() -> None:
    rules = list_watchlists()
    st.subheader("股票池与规则管理")
    metric_col1, metric_col2, metric_col3 = st.columns(3)
    metric_col1.metric("规则总数", len(rules))
    metric_col2.metric("启用中", sum(1 for rule in rules if rule.enabled))
    metric_col3.metric("默认访问地址", STREAMLIT_URL)

    with st.expander("新增规则", expanded=True):
        initial = default_rule_initial()
        apply_queued_rule_form_seed("create")
        copy_notice = st.session_state.get("create_active_notice", "")
        if copy_notice:
            st.info(copy_notice)
        raw_payload = parse_rule_form("create", initial=initial)
        st.caption(
            "切换市场后会立即刷新默认基准候选；也可以选择“自定义”手动输入指数或 ETF 代码。"
            "如果想复用现有参数，可在下方已有规则里点击“复制为新规则”。"
        )
        create_col1, create_col2 = st.columns(2)
        if create_col1.button("保存新规则", key="create_rule_submit", use_container_width=True):
            try:
                save_watchlist(normalize_rule_payload(raw_payload))
                st.session_state.pop("create_active_notice", None)
                st.success("规则已保存。")
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))
        if create_col2.button("恢复默认", key="create_rule_reset", use_container_width=True):
            queue_rule_form_seed("create", default_rule_initial())
            st.session_state.pop("create_active_notice", None)
            st.rerun()

    if not rules:
        st.info("还没有任何规则，先从上面添加一条。")
        return

    table = pd.DataFrame(
        [
            {
                "ID": rule.id,
                "启用": "是" if rule.enabled else "否",
                "市场": market_label(rule.market),
                "股票": rule.display_name,
                "代码": rule.symbol,
                "基准": f"{rule.benchmark_name} ({rule.benchmark_symbol})",
                "模式": mode_label(rule.monitor_mode),
                "轮询(分钟)": rule.poll_interval_minutes,
                "冷却(日)": rule.cooldown_trading_days,
                "上次检查": rule.last_checked_at or "-",
                "上次触发": rule.last_triggered_at or "-",
            }
            for rule in rules
        ]
    )
    st.dataframe(table, use_container_width=True, hide_index=True)

    for rule in rules:
        with st.expander(
            f"编辑 #{rule.id} | {rule.display_name} ({rule.symbol}) | "
            f"{'启用中' if rule.enabled else '已停用'}"
        ):
            initial = watchlist_to_initial(rule)
            raw_payload = parse_rule_form(f"edit_{rule.id}", initial=initial)
            if st.button("保存修改", key=f"save_{rule.id}", use_container_width=True):
                try:
                    save_watchlist(normalize_rule_payload(raw_payload), rule_id=rule.id)
                    st.success("规则已更新。")
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))

            action_col1, action_col2, action_col3 = st.columns(3)
            if action_col1.button(
                "复制为新规则",
                key=f"copy_{rule.id}",
                use_container_width=True,
            ):
                queue_rule_form_seed(
                    "create",
                    watchlist_to_initial(rule, clear_identity=True),
                    notice=f"已复制规则 #{rule.id} 的监控参数，请填写新的股票代码和名称后再保存。",
                )
                st.rerun()
            if action_col2.button(
                "停用" if rule.enabled else "启用",
                key=f"toggle_{rule.id}",
                use_container_width=True,
            ):
                set_watchlist_enabled(rule.id, not rule.enabled)
                st.rerun()
            if action_col3.button(
                "删除",
                key=f"delete_{rule.id}",
                use_container_width=True,
                type="secondary",
            ):
                delete_watchlist(rule.id)
                st.rerun()


def render_settings_page() -> None:
    settings = get_settings()
    st.subheader("系统设置与密钥配置")
    st.info("只有 Telegram 和 Finnhub 的账号信息需要你自己准备，其他环境和代码我已经在本机配置好了。")

    with st.form("settings_form"):
        telegram_bot_token = st.text_input(
            "Telegram Bot Token",
            value=settings.get("telegram_bot_token", ""),
            type="password",
        )
        telegram_chat_id = st.text_input(
            "Telegram chat_id",
            value=settings.get("telegram_chat_id", ""),
        )
        finnhub_api_key = st.text_input(
            "Finnhub API Key",
            value=settings.get("finnhub_api_key", ""),
            type="password",
        )
        submitted = st.form_submit_button("保存设置", use_container_width=True)
        if submitted:
            update_settings(
                {
                    "telegram_bot_token": telegram_bot_token.strip(),
                    "telegram_chat_id": telegram_chat_id.strip(),
                    "finnhub_api_key": finnhub_api_key.strip(),
                }
            )
            st.success("设置已保存。")
            st.rerun()

    st.markdown("**运行方式**")
    st.code(
        "\n".join(
            [
                ".\\start_app.ps1        # 启动后台监控 + 本地网页服务",
                ".\\open_ui.ps1          # 在浏览器打开本地界面",
                ".\\register_startup_task.ps1  # 配置 Windows 登录自启",
            ]
        ),
        language="powershell",
    )

    st.markdown("**你需要自己准备的账号信息**")
    st.write("- Telegram：创建 bot，拿到 bot token 和 chat_id。")
    st.write("- Finnhub：注册免费账号，生成 API Key，用于美股数据。")


def render_logs_page() -> None:
    settings = get_settings()
    alert_logs = list_alert_logs(limit=None)
    system_logs = list_system_logs(limit=None)
    st.subheader("提醒日志与运行状态")

    status_col1, status_col2, status_col3, status_col4 = st.columns(4)
    status_col1.metric("后台状态", settings.get("worker_status", "未知"))
    status_col2.metric("最近心跳", settings.get("worker_last_heartbeat", "-") or "-")
    status_col3.metric("最近摘要", settings.get("worker_last_cycle_summary", "-") or "-")
    status_col4.metric("提醒日志数", len(alert_logs))

    last_error = settings.get("worker_last_error", "")
    if last_error:
        st.warning(last_error)

    st.markdown("**运行状态详情**")
    status_table = pd.DataFrame(
        [
            {"键": key, "值": value}
            for key, value in settings.items()
        ]
    )
    st.dataframe(status_table, use_container_width=True, hide_index=True)

    st.markdown("**完整提醒日志**")
    if not alert_logs:
        st.info("暂无提醒日志。")
    else:
        alert_table = pd.DataFrame(alert_logs)
        alert_table["display_name"] = alert_table["display_name"].fillna("(已删除规则)")
        alert_table["alert_side"] = alert_table["alert_side"].map({"buy": "买入", "sell": "卖出"})
        alert_table["monitor_mode"] = alert_table["monitor_mode"].map(MODE_LABELS)
        alert_table["sent_success"] = alert_table["sent_success"].map({1: "成功", 0: "失败"})
        alert_table["payload_json"] = alert_table["payload_json"].apply(pretty_json)
        alert_table = alert_table.rename(
            columns={
                "id": "日志ID",
                "watchlist_id": "规则ID",
                "display_name": "股票名称",
                "symbol": "股票代码",
                "benchmark_symbol": "基准代码",
                "alert_side": "提醒方向",
                "monitor_mode": "监控模式",
                "stock_change_pct": "个股变化(%)",
                "benchmark_change_pct": "基准变化(%)",
                "divergence_pct": "背离值(%)",
                "message": "消息内容",
                "payload_json": "原始负载JSON",
                "sent_success": "发送结果",
                "sent_error": "发送错误",
                "created_at": "创建时间",
            }
        )
        st.dataframe(
            alert_table[
                [
                    "日志ID",
                    "规则ID",
                    "股票名称",
                    "股票代码",
                    "基准代码",
                    "提醒方向",
                    "监控模式",
                    "个股变化(%)",
                    "基准变化(%)",
                    "背离值(%)",
                    "发送结果",
                    "发送错误",
                    "创建时间",
                    "消息内容",
                    "原始负载JSON",
                ]
            ],
            use_container_width=True,
            hide_index=True,
        )

    st.markdown("**完整系统日志**")
    if not system_logs:
        st.info("暂无系统日志。")
    else:
        system_table = pd.DataFrame(system_logs)
        system_table["details_json"] = system_table["details_json"].apply(pretty_json)
        system_table = system_table.rename(
            columns={
                "id": "日志ID",
                "level": "级别",
                "category": "分类",
                "message": "消息",
                "details_json": "详细信息JSON",
                "created_at": "创建时间",
            }
        )
        st.dataframe(
            system_table[
                [
                    "日志ID",
                    "级别",
                    "分类",
                    "创建时间",
                    "消息",
                    "详细信息JSON",
                ]
            ],
            use_container_width=True,
            hide_index=True,
        )


st.title(APP_NAME)
st.caption("中低频股票择时提醒工具：支持日内背离和跨日背离，不自动下单。")

page = st.sidebar.radio(
    "页面",
    options=["股票池与规则管理", "系统设置与密钥配置", "提醒日志与运行状态"],
)

if page == "股票池与规则管理":
    render_watchlists_page()
elif page == "系统设置与密钥配置":
    render_settings_page()
else:
    render_logs_page()
