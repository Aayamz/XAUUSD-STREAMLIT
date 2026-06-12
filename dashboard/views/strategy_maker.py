"""Strategy Maker — plug in HuggingFace models and create strategies from the UI."""
from __future__ import annotations

import streamlit as st

from strategy.hf_plugin import HFPlugin, list_presets, load_preset
from strategy import create_strategy, list_strategies


def render() -> None:
    st.markdown('<div class="tb-section-label">Strategy Maker</div>', unsafe_allow_html=True)

    tab_preset, tab_custom, tab_browse = st.tabs([
        "Preset Models",
        "Custom Model",
        "Browse HuggingFace",
    ])

    # --- Tab 1: Preset Models ------------------------------------------------
    with tab_preset:
        presets = list_presets()
        if not presets:
            st.info("No preset models available.")
        else:
            col1, col2 = st.columns(2)
            preset_models = []
            for name, info in presets.items():
                preset_models.append({
                    "name": info.get("label", name),
                    "tag": name,
                    "author": info.get("repo_id", ""),
                    "desc": f"TP: {info.get('tp_points', '?')} pts | SL: {info.get('sl_points', '?')} pts | Type: {info.get('model_type', 'joblib')}",
                    "active": f"preset_{name}" == st.session_state.get("active_strategy"),
                    "icon": "🧠",
                })

            for i, m in enumerate(preset_models):
                col = col1 if i % 2 == 0 else col2
                with col:
                    featured = "sm-card-featured" if m["active"] else ""
                    active_badge = '<span style="font-size:10px;padding:2px 8px;background:#0d419d22;color:#58a6ff;border-radius:20px">Active</span>' if m["active"] else ""
                    btn_class = "sm-btn-active" if m["active"] else "sm-btn"
                    btn_label = "✓ Activated" if m["active"] else "Activate"
                    st.markdown(f"""
                    <div class="sm-card {featured}" style="margin-bottom:8px">
                      <div style="display:flex;align-items:flex-start;justify-content:space-between;margin-bottom:8px">
                        <div style="width:32px;height:32px;background:#0d1117;border-radius:8px;
                             display:flex;align-items:center;justify-content:center;font-size:16px">{m['icon']}</div>
                        {active_badge}
                      </div>
                      <div style="margin-bottom:4px">
                        <span style="font-weight:500;font-size:13px;color:#e6edf3">{m['name']}</span>
                        <span style="margin-left:6px" class="sm-code-tag">{m['tag']}</span>
                      </div>
                      <div style="font-size:11px;color:#8b949e;margin-bottom:8px">{m['desc']}</div>
                      <button class="{btn_class}">{btn_label}</button>
                    </div>""", unsafe_allow_html=True)

                    if not m["active"]:
                        if st.button(f"Activate {m['tag']}", key=f"activate_{m['tag']}", label_visibility="collapsed"):
                            try:
                                plugin = load_preset(m["tag"])
                                plugin.register(f"preset_{m['tag']}")
                                st.session_state.active_strategy = f"preset_{m['tag']}"
                                st.toast(f"Activated preset: {m['name']}", icon="✅")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Failed to activate: {e}")

    # --- Tab 2: Custom Model -------------------------------------------------
    with tab_custom:
        st.markdown(
            "Plug in any HuggingFace model or a local file to create a strategy.",
            unsafe_allow_html=False,
        )
        source = st.radio("Model source", ["HuggingFace Hub", "Local file"], horizontal=True)

        with st.form("custom_strategy_form"):
            col1, col2 = st.columns(2)
            with col1:
                strategy_name = st.text_input("Strategy name", value="my_custom_strategy")
                if source == "HuggingFace Hub":
                    repo_id = st.text_input("HuggingFace repo", value="JonusNattapong/xauusd-scalping-models")
                    model_file = st.text_input("Model filename", value="entry_clf.joblib")
                else:
                    repo_id = ""
                    model_file = st.text_input("Model file path", value="./models/my_model.pkl")

            with col2:
                model_type = st.selectbox("Model type", ["joblib", "pytorch", "onnx"])
                tp_points = st.number_input("Take Profit (points)", value=1500, min_value=10)
                sl_points = st.number_input("Stop Loss (points)", value=400, min_value=10)
                min_confidence = st.number_input("Min confidence (%)", value=50.0, min_value=0.0, max_value=100.0)
                min_rr = st.number_input("Min R:R", value=1.0, min_value=0.1, step=0.1)

            submitted = st.form_submit_button("Create Strategy", type="primary", width="stretch")

        if submitted:
            if not strategy_name.strip():
                st.error("Strategy name is required")
            elif not model_file.strip():
                st.error("Model file is required")
            else:
                try:
                    if source == "HuggingFace Hub":
                        plugin = HFPlugin.from_repo(
                            repo_id=repo_id,
                            model_file=model_file,
                            model_type=model_type,
                            tp_points=int(tp_points),
                            sl_points=int(sl_points),
                        )
                    else:
                        plugin = HFPlugin.from_local(
                            model_file,
                            model_type=model_type,
                            tp_points=int(tp_points),
                            sl_points=int(sl_points),
                        )
                    plugin.min_confidence = min_confidence
                    plugin.min_rr = min_rr

                    plugin.register(strategy_name)
                    st.session_state.active_strategy = strategy_name
                    st.toast(f"Strategy '{strategy_name}' created and activated!", icon="✅")
                    st.rerun()
                except Exception as e:
                    st.error(f"Failed to create strategy: {e}")

    # --- Tab 3: Browse HuggingFace -------------------------------------------
    with tab_browse:
        st.markdown(
            "Search HuggingFace for XAUUSD models and import them as strategies.",
            unsafe_allow_html=False,
        )
        search_query = st.text_input("Search HuggingFace", value="xauusd scalping model",
                                     placeholder="e.g. xauusd, gold trading, forex")
        if st.button("Search", type="primary"):
            with st.spinner("Searching..."):
                try:
                    from huggingface_hub import list_models
                    models = list(list_models(search=search_query, limit=10))
                    if models:
                        for m in models:
                            model_id = m.id if hasattr(m, "id") else str(m)
                            with st.expander(f"{model_id}"):
                                st.write(f"**ID**: `{model_id}`")
                                if hasattr(m, "tags"):
                                    st.write(f"**Tags**: {', '.join(m.tags) if m.tags else 'none'}")
                                if hasattr(m, "pipeline_tag"):
                                    st.write(f"**Pipeline**: {m.pipeline_tag}")
                                if st.button("Import", key=f"import_{model_id}", type="primary"):
                                    st.session_state["hf_import_repo"] = model_id
                                    st.info(f"Go to **Custom Model** tab and enter `{model_id}` as the repo.")
                    else:
                        st.info("No models found.")
                except ImportError:
                    st.error("huggingface_hub is required. Install with: `pip install huggingface_hub`")
                except Exception as e:
                    st.error(f"Search failed: {e}")

    # --- Registered strategies — card grid ------------------------------------
    st.markdown('<div class="tb-section-label" style="margin-top:16px">Registered strategies</div>',
                unsafe_allow_html=True)

    strategy_icon_map = {
        "hf_scalping":      ("📈", "HF MA crossover scalper"),
        "ema_crossover":    ("📉", "EMA crossover scalper"),
        "bollinger_bounce": ("〰️", "Bollinger band bounce"),
        "rsi_stoch":        ("🎛", "RSI + stochastic combo"),
        "grid_scalper":     ("⊞", "Grid scalper"),
        "tick_scalper":     ("⚡", "Tick / news scalper"),
        "macd_zero_line":   ("🔀", "MACD zero-line"),
        "luxalgo_smc":      ("🧩", "LuxAlgo SMC"),
    }

    strategy_desc_map = {
        "hf_scalping":      "Hybrid MA(5)/MA(20) crossover with optional ML confirmation.",
        "ema_crossover":    "Pure EMA(5)/EMA(20) crossover. Buys bullish cross, sells bearish.",
        "bollinger_bounce": "Mean reversion at BB bands with RSI filter. Best on ranging markets.",
        "rsi_stoch":        "RSI(14) + stochastic dual confirmation. Quick 5-10pt targets.",
        "grid_scalper":     "Places buy/sell orders at fixed intervals. Profits from oscillation.",
        "tick_scalper":     "Fires on volume spikes (news events). Tight TP/SL, fast execution.",
        "macd_zero_line":   "MACD zero-line cross with momentum fallback.",
        "luxalgo_smc":      "Smart-Money-Concepts - OBs, FVGs, liquidity sweeps, BOS/CHoCH.",
    }

    strategies = list_strategies()
    if not strategies:
        st.info("No strategies registered.")
    else:
        cols = st.columns(3)
        for i, s in enumerate(strategies):
            name = s["name"]
            icon, label = strategy_icon_map.get(name, ("⬛", s.get("label", name)))
            desc = strategy_desc_map.get(name, s.get("description", ""))
            is_active = (name == st.session_state.get("active_strategy"))
            btn_class = "sm-btn-active" if is_active else "sm-btn"
            btn_label = "✓ Active" if is_active else "Activate"

            with cols[i % 3]:
                st.markdown(f"""
                <div class="sm-card" style="margin-bottom:8px">
                  <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px">
                    <div style="width:28px;height:28px;background:#0d1117;border-radius:8px;
                         display:flex;align-items:center;justify-content:center;font-size:14px">{icon}</div>
                    <div style="min-width:0">
                      <div style="font-weight:500;font-size:12px;color:#e6edf3;
                           white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{label}</div>
                      <span class="sm-code-tag">{name}</span>
                    </div>
                  </div>
                  <div style="font-size:11px;color:#8b949e;margin-bottom:8px">{desc}</div>
                  <button class="{btn_class}">{btn_label}</button>
                </div>""", unsafe_allow_html=True)

                if not is_active:
                    if st.button(f"Activate {name}", key=f"activate_{name}", label_visibility="collapsed"):
                        st.session_state.active_strategy = name
                        st.rerun()
