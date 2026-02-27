"""
app.py
------
Error Code Mapping Agent — Streamlit UI

Internal error codes input:  Google Sheets / Upload (Excel, CSV) / URL
PSP documentation input:     Google Sheets / Upload (Excel, CSV, PDF) / URL
"""

import streamlit as st
import pandas as pd
from agent.ingestor import ingest, detect_file_type, is_google_sheets_url
from agent.reconciler import run_reconciliation
from agent.validator import extract_csv_from_response, validate_csv

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Error Code Mapping Agent",
    page_icon="🔁",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------

st.title("🔁 Error Code Mapping Agent")
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
        help="Opus = best quality · Sonnet = faster & cheaper",
    )
    max_tokens = st.slider(
        "Max output tokens",
        min_value=2048,
        max_value=8096,
        value=8096,
        step=512,
        help="Increase if output gets cut off.",
    )
    st.divider()
    st.markdown(
        "**Supported sources (both sides)**\n"
        "- 📊 Google Sheets (public share link)\n"
        "- 📁 Excel (.xlsx / .xls)\n"
        "- 📁 CSV (.csv)\n"
        "- 📁 PDF (.pdf) — PSP only\n"
        "- 🔗 Any public URL\n"
    )


# ---------------------------------------------------------------------------
# Reusable input widget
# ---------------------------------------------------------------------------

def source_input(side: str, accept_pdf: bool):
    """
    Render the input method selector for one side.

    Parameters
    ----------
    side       : 'internal' or 'psp'  — used to key widgets uniquely
    accept_pdf : whether to include PDF as an upload option

    Returns
    -------
    source       : the raw source (URL string, UploadedFile, or None)
    source_name  : a string label used for detect_file_type
    """
    upload_types = ["xlsx", "xls", "csv"] + (["pdf"] if accept_pdf else [])
    upload_label = "Upload Excel / CSV" + (" / PDF" if accept_pdf else "")

    method = st.radio(
        "Input method",
        ["📊 Google Sheets", "📁 Upload file", "🔗 URL"],
        key=f"method_{side}",
        horizontal=True,
    )

    source = None
    source_name = None

    if method == "📊 Google Sheets":
        st.info(
            "Share your sheet first:\n\n"
            "**File → Share → Share with others → "
            "Anyone with the link → Viewer → Copy link**"
        )
        gs_url = st.text_input(
            "Paste Google Sheets link",
            placeholder="https://docs.google.com/spreadsheets/d/...",
            key=f"gs_{side}",
        )
        if gs_url.strip():
            if is_google_sheets_url(gs_url.strip()):
                source = gs_url.strip()
                source_name = gs_url.strip()
                st.success("✅ Google Sheets link detected")
            else:
                st.error("That doesn't look like a Google Sheets URL. Please paste the full sharing link.")

    elif method == "📁 Upload file":
        uploaded = st.file_uploader(
            upload_label,
            type=upload_types,
            key=f"upload_{side}",
        )
        if uploaded:
            source = uploaded
            source_name = uploaded.name
            st.success(f"✅ Loaded: {uploaded.name}")

    else:  # URL
        url = st.text_input(
            "Paste URL",
            placeholder="https://raw.githubusercontent.com/... or any public file URL",
            key=f"url_{side}",
        )
        if url.strip():
            source = url.strip()
            source_name = url.strip()

    return source, source_name


# ---------------------------------------------------------------------------
# Input panels
# ---------------------------------------------------------------------------

col_left, col_right = st.columns(2, gap="large")

with col_left:
    st.subheader("📋 Internal Error Codes")
    internal_source, internal_name = source_input("internal", accept_pdf=False)

with col_right:
    st.subheader("📄 PSP Documentation")
    psp_source, psp_name = source_input("psp", accept_pdf=True)

st.divider()

# ---------------------------------------------------------------------------
# Run button
# ---------------------------------------------------------------------------

ready = internal_source is not None and psp_source is not None

run_clicked = st.button(
    "🚀 Run Error Code Mapping",
    type="primary",
    use_container_width=True,
    disabled=not ready,
)

if not ready:
    st.info("Provide both inputs above to enable the Run button.")

# ---------------------------------------------------------------------------
# Agent execution
# ---------------------------------------------------------------------------

if run_clicked:
    with st.status("🤖 Running error code mapping agent...", expanded=True) as status:

        # Step 1 — ingest internal errors
        st.write("📥 Step 1 / 4 — Ingesting internal error codes...")
        try:
            internal_type = detect_file_type(internal_name or "file.xlsx")
            internal_text = ingest(internal_source, internal_type)
            label = "Google Sheets" if internal_type == "google_sheets" else internal_type.upper()
            st.write(f"   → Parsed as **{label}** ✅")
        except PermissionError as e:
            status.update(label="Google Sheets access denied", state="error")
            st.error(str(e))
            st.stop()
        except Exception as e:
            status.update(label="Failed at Step 1", state="error")
            st.error(f"Could not ingest internal error codes: {e}")
            st.stop()

        # Step 2 — ingest PSP docs
        st.write("📥 Step 2 / 4 — Ingesting PSP documentation...")
        try:
            psp_type = detect_file_type(psp_name or "file.pdf")
            psp_text = ingest(psp_source, psp_type)
            label = "Google Sheets" if psp_type == "google_sheets" else psp_type.upper()
            chars = f"{len(psp_text):,} characters"
            st.write(f"   → Parsed as **{label}** ({chars}) ✅")
        except PermissionError as e:
            status.update(label="Google Sheets access denied", state="error")
            st.error(str(e))
            st.stop()
        except Exception as e:
            status.update(label="Failed at Step 2", state="error")
            st.error(f"Could not ingest PSP documentation: {e}")
            st.stop()

        # Step 3 — Claude
        st.write(
            f"🧠 Step 3 / 4 — Running 4-phase mapping analysis "
            f"via **{model_choice}** (30–90 seconds)..."
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
            st.write(f"   → {validation['stats'].get('total_rows', 0)} rows parsed ✅")

        status.update(
            label="✅ Mapping complete!" if validation["valid"] else "⚠️ Complete with warnings",
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

        # Metrics
        m1, m2, m3, m4, m5, m6 = st.columns(6)
        m1.metric("Total rows", stats.get("total_rows", 0))
        m2.metric("Forward", stats.get("forward", 0))
        m3.metric("Reverse", stats.get("reverse", 0))
        m4.metric("PSP-only", stats.get("psp_only", 0))
        m5.metric("Unmapped", stats.get("unmapped", 0))
        m6.metric("Avg confidence", f"{stats.get('avg_confidence', 0)}%")

        # Mapping type breakdown
        with st.expander("📈 Mapping type breakdown", expanded=False):
            st.dataframe(
                pd.DataFrame({
                    "Mapping Type": ["Exact", "Probable", "One-to-many", "Closest partial"],
                    "Count": [
                        stats.get("exact", 0),
                        stats.get("probable", 0),
                        stats.get("one_to_many", 0),
                        stats.get("closest_partial", 0),
                    ],
                }),
                use_container_width=True,
                hide_index=True,
            )

        # Validation result
        if validation["issues"]:
            st.error("🚨 Validation issues — review before production use:")
            for issue in validation["issues"]:
                st.write(f"  • {issue}")
        elif validation["warnings"]:
            st.warning("⚠️ Minor warnings (non-blocking):")
            for w in validation["warnings"]:
                st.write(f"  • {w}")
        else:
            st.success("🎉 All quality checks passed!")

        # Filterable table
        st.divider()
        st.subheader("🔍 Explore Mappings")

        fc1, fc2, fc3 = st.columns(3)
        with fc1:
            dir_filter = st.multiselect(
                "Direction",
                options=df["direction"].dropna().unique().tolist(),
                default=df["direction"].dropna().unique().tolist(),
            )
        with fc2:
            type_filter = st.multiselect(
                "Mapping type",
                options=df["mapping_type"].dropna().unique().tolist(),
                default=df["mapping_type"].dropna().unique().tolist(),
            )
        with fc3:
            min_conf = st.slider("Min confidence", 0, 100, 0)

        filtered_df = df[
            df["direction"].isin(dir_filter) &
            (df["mapping_type"].isin(type_filter) | df["mapping_type"].isna()) &
            (df["confidence"] >= min_conf)
        ]

        st.dataframe(filtered_df, use_container_width=True, height=450)
        st.caption(f"Showing {len(filtered_df)} of {len(df)} rows")

        # Download
        st.divider()
        st.download_button(
            label="⬇️ Download Full CSV",
            data=csv_string,
            file_name="error_code_mapping.csv",
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
    "Error Code Mapping Agent · Built with Claude + Streamlit · "
    "Deployed on Render"
)
