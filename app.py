"""
app.py
------
Error Code Mapping Agent — Streamlit UI

Internal error codes:  Google Sheets / Upload (Excel, CSV) / URL
PSP documentation:     Google Sheets / Upload (Excel, CSV, PDF) / URL

Features:
- Domain context input to guide Claude
- Automatic second investigation pass on 'Needs investigation' rows
- Filterable results table + download
"""

import streamlit as st
import pandas as pd
import csv
from io import StringIO
from agent.ingestor import ingest, detect_file_type, is_google_sheets_url
from agent.reconciler import (
    run_reconciliation,
    run_investigation_pass,
    merge_investigation_results,
)
from agent.validator import extract_csv_from_response, validate_csv

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Error Code Mapping Agent",
    page_icon="🔁",
    layout="wide",
    initial_sidebar_state="expanded",
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
# Sidebar — settings + domain context
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
    )

    st.divider()
    st.header("🔍 Second Investigation Pass")
    run_second_pass = st.toggle(
        "Auto-run on 'Needs investigation' rows",
        value=True,
        help=(
            "After the main mapping, Claude will retry all 'Needs investigation' rows "
            "with a lower confidence threshold to reduce unmapped count."
        ),
    )

    st.divider()
    st.header("🗂️ Domain Context")
    st.caption(
        "Tell Claude about your platform and PSP to improve mapping accuracy. "
        "The more detail you provide, the fewer 'Needs investigation' rows you'll get."
    )
    domain_context = st.text_area(
        "Domain hints (optional)",
        height=220,
        placeholder=(
            "Examples:\n"
            "- PSP is BCA FIRe API (Indonesian banking)\n"
            "- Internal codes PF0001xx = beneficiary-side errors\n"
            "- Internal codes PF0002xx = network/routing errors\n"
            "- Internal codes PF003xx  = compliance/KYC errors\n"
            "- Retry is safe for network errors but NOT for compliance\n"
            "- 'No PSP equivalent' expected for all funding workflow codes\n"
            "- Platform supports UPI/PIX; PSP is bank-only"
        ),
        help="This is injected into Claude's context before mapping begins.",
    )

    st.divider()
    st.markdown(
        "**Supported input sources**\n"
        "- 📊 Google Sheets (public share link)\n"
        "- 📁 Excel / CSV / PDF upload\n"
        "- 🔗 Any public file URL\n"
    )


# ---------------------------------------------------------------------------
# Reusable input widget
# ---------------------------------------------------------------------------

def source_input(side: str, accept_pdf: bool):
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
            "Share first: **File → Share → Anyone with the link → Viewer → Copy link**"
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
                st.error("Doesn't look like a Google Sheets URL. Paste the full sharing link.")

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

    else:
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
    total_steps = 6 if run_second_pass else 4
    with st.status("🤖 Running error code mapping agent...", expanded=True) as status:

        # Step 1 — ingest internal errors
        st.write("📥 Step 1 — Ingesting internal error codes...")
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
        st.write("📥 Step 2 — Ingesting PSP documentation...")
        try:
            psp_type = detect_file_type(psp_name or "file.pdf")
            psp_text = ingest(psp_source, psp_type)
            label = "Google Sheets" if psp_type == "google_sheets" else psp_type.upper()
            st.write(f"   → Parsed as **{label}** ({len(psp_text):,} chars) ✅")
        except PermissionError as e:
            status.update(label="Google Sheets access denied", state="error")
            st.error(str(e))
            st.stop()
        except Exception as e:
            status.update(label="Failed at Step 2", state="error")
            st.error(f"Could not ingest PSP documentation: {e}")
            st.stop()

        # Step 3 — domain context
        if domain_context.strip():
            st.write(f"🗂️ Step 3 — Domain context loaded ({len(domain_context.split())} words) ✅")
        else:
            st.write("🗂️ Step 3 — No domain context provided (add in sidebar to improve results)")

        # Step 4 — Main Claude pass
        st.write(f"🧠 Step 4 — Running 4-phase mapping via **{model_choice}** (30–90s)...")
        try:
            raw_response = run_reconciliation(
                internal_errors_text=internal_text,
                psp_documentation_text=psp_text,
                domain_context=domain_context,
                model=model_choice,
                max_tokens=max_tokens,
            )
            st.write("   → Main mapping response received ✅")
        except EnvironmentError as e:
            status.update(label="API key missing", state="error")
            st.error(str(e))
            st.stop()
        except Exception as e:
            status.update(label="Claude API error", state="error")
            st.error(f"Claude API error: {e}")
            st.stop()

        # Extract CSV from main pass
        csv_string = extract_csv_from_response(raw_response)

        # Step 5 — Investigation pass (optional)
        if run_second_pass:
            st.write("🔍 Step 5 — Extracting 'Needs investigation' rows for second pass...")
            try:
                main_df = pd.read_csv(
                    StringIO(csv_string),
                    quoting=csv.QUOTE_MINIMAL,
                    on_bad_lines="skip",
                    dtype=str,
                )
                main_df.columns = [c.strip() for c in main_df.columns]

                ni_mask = (
                    main_df.get("unknown_subtype", pd.Series(dtype=str))
                    .astype(str).str.strip() == "Needs investigation"
                )
                ni_df = main_df[ni_mask]
                ni_count = len(ni_df)

                if ni_count > 0:
                    st.write(f"   → Found **{ni_count}** 'Needs investigation' rows — retrying...")
                    ni_csv = ni_df.to_csv(index=False)

                    inv_response = run_investigation_pass(
                        needs_investigation_csv=ni_csv,
                        psp_documentation_text=psp_text,
                        domain_context=domain_context,
                        model=model_choice,
                        max_tokens=4096,
                    )
                    inv_csv = extract_csv_from_response(inv_response)

                    # Step 6 — Merge
                    st.write("🔀 Step 6 — Merging investigation results...")
                    csv_string = merge_investigation_results(csv_string, inv_csv)

                    # Count how many got resolved
                    try:
                        merged_df = pd.read_csv(StringIO(csv_string), dtype=str, on_bad_lines="skip")
                        merged_df.columns = [c.strip() for c in merged_df.columns]
                        still_ni = (
                            merged_df.get("unknown_subtype", pd.Series(dtype=str))
                            .astype(str).str.strip() == "Needs investigation"
                        ).sum()
                        resolved = ni_count - still_ni
                        st.write(f"   → **{resolved}** rows resolved · **{still_ni}** still need investigation ✅")
                    except Exception:
                        st.write("   → Merge complete ✅")
                else:
                    st.write("   → No 'Needs investigation' rows found — skipping second pass ✅")

            except Exception as e:
                st.warning(f"Second pass failed (continuing with main results): {e}")

        # Final validation
        st.write("✅ Final step — Validating output quality...")
        validation = validate_csv(csv_string)
        if validation["df"] is not None:
            st.write(f"   → {validation['stats'].get('total_rows', 0)} rows in final output ✅")

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

        # Mapping breakdown
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

        # Validation
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

        # Tips if unmapped count is still high
        unmapped_count = stats.get("unmapped", 0)
        total = stats.get("total_rows", 1)
        if unmapped_count / total > 0.3:
            with st.expander("💡 Tips to reduce unmapped rows", expanded=False):
                st.markdown("""
**You have >30% unmapped rows. Try these to improve:**

1. **Add domain context** in the sidebar — tell Claude your PSP name, error code ranges, and platform type
2. **Enrich your internal error sheet** — add columns: `failure_domain`, `expected_action`, `is_psp_facing`, `example_scenario`
3. **Check your PSP PDF** — make sure it contains the full error code list (not just a summary)
4. **Structural gaps are normal** — 'No PSP equivalent' rows (funding/approval/RFI workflows) will always be unmapped by design
                """)

        # Filterable table
        st.divider()
        st.subheader("🔍 Explore Mappings")

        fc1, fc2, fc3 = st.columns(3)
        with fc1:
            dir_opts = df["direction"].dropna().unique().tolist()
            dir_filter = st.multiselect("Direction", options=dir_opts, default=dir_opts)
        with fc2:
            type_opts = df["mapping_type"].dropna().unique().tolist()
            type_filter = st.multiselect("Mapping type", options=type_opts, default=type_opts)
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
st.caption("Error Code Mapping Agent · Built with Claude + Streamlit · Deployed on Render")
