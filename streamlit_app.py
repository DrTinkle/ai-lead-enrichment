import streamlit as st
from app.services.enrichment import enrich_company
from app.services.scoring import apply_acquisition_scoring

st.set_page_config(
    page_title="AI Lead Enrichment",
    layout="wide"
)

st.title("AI-Powered Lead Enrichment")
st.markdown("Analyze a company domain and evaluate it against a defined acquisition thesis.")

# ---- Sidebar: simple thesis selection ----
st.sidebar.header("Acquisition Thesis")

selected_sector = st.sidebar.selectbox(
    "Target Sector",
    ["Fintech", "SaaS", "Internet / Technology", "Healthcare", "Retail", "E-commerce"],
    index=0
)

selected_region = st.sidebar.selectbox(
    "Target Region",
    ["United States", "Europe", "Asia", "Global"],
    index=0
)

selected_maturity = st.sidebar.selectbox(
    "Target Maturity Stage",
    ["Startup", "Growth", "Mature"],
    index=1
)

# input field
domain = st.text_input("Company domain (e.g. stripe.com)")

if st.button("Analyze"):

    if not domain.strip():
        st.warning("Please enter a valid domain.")
    else:
        with st.spinner("Running enrichment pipeline..."):
            result = enrich_company(domain)

        company = result.get("company", {})
        analysis = result.get("analysis", {})

        st.divider()

        # ---- Company Overview ----
        st.subheader("Company Overview")

        col1, col2 = st.columns(2)

        with col1:
            st.write("**Name:**", company.get("name"))
            st.write("**Website:**", company.get("website"))
            st.write("**Industry:**", company.get("industry"))

        with col2:
            st.write("**Location:**", company.get("location"))
            st.write("**Size Estimate:**", company.get("size_estimate"))

        # ---- AI Analysis ----
        if analysis:
            st.divider()
            st.subheader("AI Analysis")

            st.write("**Summary**")
            st.write(analysis.get("summary"))

            col3, col4 = st.columns(2)

            with col3:
                st.write("**Sector Classification:**")
                st.write(analysis.get("sector_classification"))

                st.write("**Maturity Stage:**")
                st.write(analysis.get("maturity_stage"))

            with col4:
                st.metric("AI Score", analysis.get("acquisition_fit_score"))

        # ---- Final Scoring ----
        if analysis:
            st.divider()
            st.subheader("Final Evaluation")

            scoring = apply_acquisition_scoring(
                company,
                analysis,
                preferred_sectors=[selected_sector],
                preferred_regions=[selected_region],
                preferred_maturity=[selected_maturity],
                weight_ai=0.6,
                weight_rules=0.4
            )

            ai_score = scoring["ai_score"]
            rule_score = scoring["rule_score"]
            final_score = scoring["final_score"]

            colA, colB, colC = st.columns(3)

            with colA:
                st.metric("AI Score", ai_score)

            with colB:
                st.metric("Rule Score", rule_score)

            with colC:
                st.metric("Final Score", final_score)

            st.write("### Scoring Breakdown")

            st.write(f"Final Score = (AI × {scoring['weight_ai']}) + "
                    f"(Rules × {scoring['weight_rules']})")

            st.write(f"= ({ai_score} × {scoring['weight_ai']}) + "
                    f"({rule_score} × {scoring['weight_rules']})")

            st.write(f"= {final_score}")

            if final_score >= 8:
                st.success(f"Strong Candidate ({final_score}/10)")
            elif final_score >= 5:
                st.warning(f"Moderate Candidate ({final_score}/10)")
            else:
                st.error(f"Weak Candidate ({final_score}/10)")

            st.write("### Rule Adjustments")

            for adj in scoring["adjustments"]:
                st.write(f"- {adj}")