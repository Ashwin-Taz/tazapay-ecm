"""
app.py
------
Streamlit UI for the Payments Reconciliation Agent.
Supports file upload AND URL-based ingestion for both
internal error codes (Excel/CSV) and PSP documentation (PDF).
"""

import streamlit as st
import pandas as pd
from agent.ingestor import ingest, detect_file_type
from agent.reconciler import run_reconciliation
from agent.validator import extract_csv_from_response, validate_csv

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Payments Reconciliation Agent",
    page_icon="💳",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------

st.title("💳 Payments Reconciliation Agent")
st.caption(
    "Bidirectional error code mapping between your internal platform and PSP documentation · "
    "Powered by Claude"
)
st.divider()

# ---------------------------------------------------------------------------
# Sidebar — settings
# ---------------------------------------------------------------------------

with st.sidebar:
    st.header("⚙️ Settings")
    model_choice = st.selectbox(
        "Claude model",
        options=["claude-opus-4-6", "claude-sonnet-4-6"],
        index=0,
        help="Opus gives best reasoning quality. Sonnet is faster and cheaper.",
    )
    max_tokens = st.slider(
        "Max output tokens",
        min_value=2048,
        max_value=8096,
        value=8096,
        step=512,
        help="Increase if your output gets cut off.",
    )
    st.divider()
    st.markdown(
        "**Supported URL types**\n"
        "- GitHub raw URLs\n"
        "- S3 / Azure Blob (public)\n"
        "- Google Drive (`export=download`)\n"
        "- Dropbox (`?dl=1`)\n"
        "- Any direct `.xlsx` / `.csv` / `.pdf` URL"
    )

# ---------------------------------------------------------------------------
# Input columns
# ---------------------------------------------------------------------------

col_left, col_right = st.columns(2, gap="large")

# ---- Internal Error Codes ----
with col_left:
    st.subheader("📋 Internal Error Codes")
    mode_internal = st.radio(
        "Input method",
        ["📁 Upload file", "🔗 URL"],
        key="mode_internal",
        horizontal=True,
    )

    internal_source = None
    internal_filename = None

    if mode_internal == "📁 Upload file":
        uploaded_internal = st.file_uploader(
            "Upload Excel or CSV",
            type=["xlsx", "xls", "csv"],
            key="upload_internal",
        )
        if uploaded_internal:
            internal_source = uploaded_internal
            internal_filename = uploaded_internal.name
            st.success(f"✅ Loaded: {uploaded_internal.name}")
    else:
        url_internal = st.text_input(
            "Paste URL",
            placeholder="https://raw.githubusercontent.com/.../errors.xlsx",
            key="url_internal",
        )
        if url_internal.strip():
            internal_source = url_internal.strip()
            internal_filename = url_internal.strip()

# ---- PSP Documentation ----
with col_right:
    st.subheader("📄 PSP Documentation")
    mode_psp = st.radio(
        "Input method",
        ["📁 Upload file", "🔗 URL"],
        key="mode_psp",
        horizontal=True,
    )

    psp_source = None
    psp_filename = None

    if mode_psp == "📁 Upload file":
        uploaded_psp = st.file_uploader(
            "Upload PDF",
            type=["pdf"],
            key="upload_psp",
        )
        if uploaded_psp:
            psp_source = uploaded_psp
            psp_filename = uploaded_psp.name
            st.success(f"✅ Loaded: {uploaded_psp.name}")
    else:
        url_psp = st.text_input(
            "Paste URL",
            placeholder="https://raw.githubusercontent.com/.../psp_docs.pdf",
            key="url_psp",
        )
        if url_psp.strip():
            psp_source = url_psp.strip()
            psp_filename = url_psp.strip()

st.divider()

# ---------------------------------------------------------------------------
# Run button
# ---------------------------------------------------------------------------

run_clicked = st.button(
    "🚀 Run Reconciliation",
    type="primary",
    use_container_width=True,
    disabled=(internal_source is None or psp_source is None),
)

if internal_source is None or psp_source is None:
    st.info("Provide both inputs above to enable the Run button.")

# ---------------------------------------------------------------------------
# Agent execution
# ---------------------------------------------------------------------------

if run_clicked:
    with st.status("🤖 Running reconciliation agent...", expanded=True) as status:

        # Step 1 — ingest internal errors
        st.write("📥 Step 1 / 4 — Ingesting internal error codes...")
        try:
            internal_file_type = detect_file_type(
                internal_filename if internal_filename else "file.xlsx"
            )
            internal_text = ingest(internal_source, internal_file_type)
            st.write(f"   → Parsed as **{internal_file_type.upper()}** ✅")
        except Exception as e:
            status.update(label="Failed at Step 1", state="error")
            st.error(f"Could not ingest internal error codes: {e}")
            st.stop()

        # Step 2 — ingest PSP docs
        st.write("📥 Step 2 / 4 — Ingesting PSP documentation...")
        try:
            psp_text = ingest(psp_source, "pdf")
            st.write(f"   → Extracted {len(psp_text):,} characters from PDF ✅")
        except Exception as e:
            status.update(label="Failed at Step 2", state="error")
            st.error(f"Could not ingest PSP documentation: {e}")
            st.stop()

        # Step 3 — Claude reasoning
        st.write(
            f"🧠 Step 3 / 4 — Running 4-phase mapping analysis "
            f"via **{model_choice}** (this may take 30–90 seconds)..."
        )
        try:
            raw_response = run_reconciliation(
                internal_errors_text=internal_text,
                psp_documentation_text=psp_text,
                model=model_choice,
                max_tokens=max_tokens,
            )
            st.write("   → Claude response received ✅")
        except EnvironmentError as e:
            status.update(label="API key missing", state="error")
            st.error(str(e))
            st.stop()
        except Exception as e:
            status.update(label="Claude API error", state="error")
            st.error(f"Claude API error: {e}")
            st.stop()

        # Step 4 — validate
        st.write("✅ Step 4 / 4 — Validating output quality...")
        csv_string = extract_csv_from_response(raw_response)
        validation = validate_csv(csv_string)

        if validation["df"] is not None:
            st.write(
                f"   → {validation['stats'].get('total_rows', 0)} rows parsed ✅"
            )

        status.update(
            label="✅ Reconciliation complete!" if validation["valid"] else "⚠️ Complete with warnings",
            state="complete",
        )

    # -----------------------------------------------------------------------
    # Results
    # -----------------------------------------------------------------------

    st.divider()
    st.subheader("📊 Results")

    if validation["df"] is not None:
        stats = validation["stats"]
        df = validation["df"]

        # ---- Metric cards ----
        m1, m2, m3, m4, m5, m6 = st.columns(6)
        m1.metric("Total rows", stats.get("total_rows", 0))
        m2.metric("Forward", stats.get("forward", 0))
        m3.metric("Reverse", stats.get("reverse", 0))
        m4.metric("PSP-only", stats.get("psp_only", 0))
        m5.metric("Unmapped", stats.get("unmapped", 0))
        m6.metric("Avg confidence", f"{stats.get('avg_confidence', 0)}%")

        # ---- Mapping type breakdown ----
        with st.expander("📈 Mapping type breakdown", expanded=False):
            type_data = {
                "Mapping Type": ["Exact", "Probable", "One-to-many", "Closest partial"],
                "Count": [
                    stats.get("exact", 0),
                    stats.get("probable", 0),
                    stats.get("one_to_many", 0),
                    stats.get("closest_partial", 0),
                ],
            }
            st.dataframe(pd.DataFrame(type_data), use_container_width=True, hide_index=True)

        # ---- Validation issues ----
        if validation["issues"]:
            st.error("🚨 Validation issues found — review before using in production:")
            for issue in validation["issues"]:
                st.write(f"  • {issue}")
        elif validation["warnings"]:
            st.warning("⚠️ Minor warnings (non-blocking):")
            for w in validation["warnings"]:
                st.write(f"  • {w}")
        else:
            st.success("🎉 All quality checks passed!")

        # ---- Data table with filters ----
        st.divider()
        st.subheader("🔍 Explore Mappings")

        filter_col1, filter_col2, filter_col3 = st.columns(3)
        with filter_col1:
            dir_filter = st.multiselect(
                "Direction",
                options=df["direction"].dropna().unique().tolist(),
                default=df["direction"].dropna().unique().tolist(),
            )
        with filter_col2:
            type_filter = st.multiselect(
                "Mapping type",
                options=df["mapping_type"].dropna().unique().tolist(),
                default=df["mapping_type"].dropna().unique().tolist(),
            )
        with filter_col3:
            min_conf = st.slider("Min confidence", 0, 100, 0)

        filtered_df = df[
            df["direction"].isin(dir_filter) &
            (df["mapping_type"].isin(type_filter) | df["mapping_type"].isna()) &
            (df["confidence"] >= min_conf)
        ]

        st.dataframe(
            filtered_df,
            use_container_width=True,
            height=450,
        )
        st.caption(f"Showing {len(filtered_df)} of {len(df)} rows")

        # ---- Download ----
        st.divider()
        st.download_button(
            label="⬇️ Download Full CSV",
            data=csv_string,
            file_name="reconciliation_mapping.csv",
            mime="text/csv",
            use_container_width=True,
            type="primary",
        )

    else:
        st.error("❌ Could not parse CSV from Claude's response.")
        with st.expander("Raw Claude response (for debugging)"):
            st.text_area("Response", raw_response, height=400)

# ---------------------------------------------------------------------------
# Footer
# ---------------------------------------------------------------------------

st.divider()
st.caption(
    "Reconciliation Agent · Built with Claude + Streamlit · "
    "Deploy on Render · "
    "[GitHub](https://github.com) · "
    "Questions? Contact your payments ops team."
)
