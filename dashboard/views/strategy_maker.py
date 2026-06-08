"""Strategy Maker — plug in HuggingFace models and create strategies from the UI."""
from __future__ import annotations

import streamlit as st

from strategy.hf_plugin import HFPlugin, list_presets, load_preset
from strategy import create_strategy, list_strategies


def render() -> None:
    st.markdown('<p class="xc-section-title">Strategy Maker</p>', unsafe_allow_html=True)

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
            st.markdown(
                "Pre-configured models from the community. Click **Activate** to use one as your scalping strategy.",
                unsafe_allow_html=False,
            )
            for name, info in presets.items():
                with st.expander(f"{info.get('label', name)} — {info.get('repo_id', '')}", expanded=False):
                    st.markdown(f"""
                    | Field | Value |
                    |-------|-------|
                    | **Repo** | `{info.get('repo_id', '')}` |
                    | **Model** | `{info.get('model_file', '')}` |
                    | **Type** | {info.get('model_type', 'joblib')} |
                    | **TP** | {info.get('tp_points', '?')} pts |
                    | **SL** | {info.get('sl_points', '?')} pts |
                    """, unsafe_allow_html=False)
                    if st.button("Activate", key=f"activate_{name}", type="primary"):
                        try:
                            plugin = load_preset(name)
                            plugin.register(f"preset_{name}")
                            st.session_state.active_strategy = f"preset_{name}"
                            st.toast(f"Activated preset: {info.get('label', name)}", icon="✅")
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

                    # Register the strategy
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

    # --- Active strategies list ----------------------------------------------
    st.divider()
    st.markdown('<p class="xc-section-title">Registered Strategies</p>', unsafe_allow_html=True)
    strategies = list_strategies()
    if not strategies:
        st.info("No strategies registered.")
    else:
        for s in strategies:
            active = s["name"] == st.session_state.get("active_strategy")
            badge = "🟢 ACTIVE" if active else ""
            st.markdown(
                f"**{s.get('label', s['name'])}** `{s['name']}` {badge}  \n"
                f"<small style='color:var(--text-muted)'>{s.get('description', '')}</small>",
                unsafe_allow_html=True,
            )
