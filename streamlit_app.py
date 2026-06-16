import streamlit as st
from pathlib import Path
from app.services.enrichment import build_company_object, parse_llm_result
from app.services.data_sources import fetch_company_from_abstractapi, fetch_company_site_signal
from app.services.news import fetch_news
from app.services.funding import fetch_funding
from app.services.jobs import fetch_job_postings
from app.services.techstack import fetch_techstack
from app.services.github import fetch_github
from app.services.financials import fetch_financials
from app.services.llm import analyze_company
from app.services.cache import load_from_cache, save_to_cache
from app.services.scoring import apply_acquisition_scoring
from app.utils.cleaners import normalize_domain

st.set_page_config(page_title="Lead Enrichment Engine", layout="wide", initial_sidebar_state="expanded")

# Load external CSS
css = Path(__file__).parent / "style.css"
st.markdown(f"<style>{css.read_text()}</style>", unsafe_allow_html=True)

# Sidebar
SECTORS = ["Any Sector","AI / Machine Learning","SaaS","Fintech","Cybersecurity",
    "Data & Analytics","Healthcare","Biotech / Life Sciences","Insurance / InsurTech",
    "EdTech","PropTech","LegalTech","HR Tech","Supply Chain / Logistics",
    "Clean Energy / CleanTech","Media & Entertainment","Gaming","Telecommunications",
    "E-commerce","Retail","Food & Beverage","Travel & Hospitality","Manufacturing",
    "Real Estate","Internet / Technology","Developer Tools","Infrastructure / Cloud","Consumer"]
REGIONS = ["Any Region","United States","Canada","United Kingdom","Germany","France",
    "Netherlands","Sweden","Israel","India","Singapore","Australia","Japan",
    "Brazil","Mexico","South Korea","North America","Europe","APAC","LATAM","MENA"]
MATURITIES = ["Any Stage","Pre-Seed","Seed","Startup","Early Growth",
    "Growth","Scale-Up","Mature","Public"]

with st.sidebar:
    st.markdown('<div class="sb-brand"><div class="sb-brand-name">Lead Engine</div><div class="sb-brand-tag">Acquisition Intelligence</div></div>', unsafe_allow_html=True)
    st.markdown('<div class="sb-section">Investment Thesis</div>', unsafe_allow_html=True)
    selected_sector   = st.selectbox("Target Sector",  SECTORS,    index=0)
    selected_region   = st.selectbox("Target Region",  REGIONS,    index=0)
    selected_maturity = st.selectbox("Maturity Stage", MATURITIES, index=0)
    st.markdown('<div class="sb-section">Scoring Weights</div>', unsafe_allow_html=True)
    weight_ai    = st.slider("AI Weight", 0.0, 1.0, 0.6, 0.05)
    weight_rules = round(1.0 - weight_ai, 2)
    st.caption(f"Rule weight: **{weight_rules}**")
    st.markdown("---")
    st.markdown(
        f'<div style="font-size:12px;color:#4a5568;line-height:2;">Active thesis<br>'
        f'<span class="thesis-chip">{selected_sector}</span>'
        f'<span class="thesis-chip">{selected_region}</span>'
        f'<span class="thesis-chip">{selected_maturity}</span></div>',
        unsafe_allow_html=True)

# Page header
st.markdown(
    '<div class="page-header">'
    '<div class="page-eyebrow">Acquisition Intelligence</div>'
    '<div class="page-title">Company Enrichment &amp; Scoring</div>'
    '<div class="page-desc">Enter a domain to run the full enrichment pipeline.</div>'
    '</div>', unsafe_allow_html=True)

# Search form
with st.form("search_form"):
    col_i, col_b = st.columns([5, 1])
    with col_i:
        domain = st.text_input("Domain", placeholder="e.g. stripe.com", label_visibility="collapsed")
    with col_b:
        submitted = st.form_submit_button("Analyse ->")

# Helpers
GROWTH_C = {"strong":"#3fb950","moderate":"#e3b341","weak":"#f85149",
    "declining":"#f85149","positive":"#3fb950","negative":"#f85149","mixed":"#e3b341","neutral":"#8b9eb0"}

def pill(text, color):
    return (f'<span style="background:{color}22;color:{color};border:1px solid {color}44;'
            f'border-radius:100px;padding:4px 14px;font-size:12px;font-weight:700;'
            f'text-transform:uppercase;letter-spacing:.06em;">{text}</span>')

def score_bar(label, value, max_val, color):
    pct = min(100, round(value / max_val * 100)) if max_val else 0
    return (f'<div class="score-bar-wrap">'
            f'<div class="score-bar-header"><span>{label}</span><span>{value:.1f} / {max_val:.0f}</span></div>'
            f'<div class="score-bar-track"><div class="score-bar-fill" style="width:{pct}%;background:{color};"></div></div>'
            f'</div>')

def fmt_usd(v):
    if v is None: return "--"
    if v >= 1e9: return "$%.2fB" % (v/1e9)
    return "$%.1fM" % (v/1e6)

def fmt_pct(v):
    if v is None: return "--"
    return "%+.1f%%" % (v*100)

def fmt_x(v):
    if v is None: return "--"
    return "%.1fx" % v

# Pipeline
if submitted:
    if not domain.strip():
        st.warning("Please enter a valid domain.")
        st.stop()

    clean_domain = normalize_domain(domain.strip())
    cached = load_from_cache(clean_domain)

    if cached:
        company    = cached.get("company", {})
        analysis   = cached.get("analysis", {})
        funding    = cached.get("funding")
        jobs       = cached.get("jobs")
        news       = cached.get("news")
        techstack  = cached.get("techstack")
        github     = cached.get("github")
        financials = cached.get("financials")
    else:
        with st.status("Running enrichment pipeline...", expanded=True) as status:
            st.write("Fetching company identity from AbstractAPI...")
            api_data = fetch_company_from_abstractapi(clean_domain)
            st.write("Scraping website...")
            site_signal = fetch_company_site_signal(clean_domain)
            company_obj, homepage_html = build_company_object(clean_domain, api_data, site_signal)
            st.write("Searching for recent news (GDELT / NewsAPI)...")
            news = fetch_news(company_obj.name, clean_domain)
            st.write("Checking SEC EDGAR for funding signals...")
            funding = fetch_funding(company_name=company_obj.name, domain=clean_domain,
                                    news_articles=(news or {}).get("articles", []))
            st.write("Scanning job postings (Adzuna + careers page)...")
            jobs = fetch_job_postings(company_obj.name, clean_domain,
                                      industry=company_obj.industry)
            st.write("Detecting tech stack from HTML...")
            techstack = fetch_techstack(clean_domain, existing_html=homepage_html or None)
            st.write("Fetching GitHub engineering signals...")
            github = fetch_github(company_obj.name, clean_domain)
            st.write("Checking public market financials (Yahoo Finance)...")
            financials = fetch_financials(company_obj.name, clean_domain)
            st.write("Running AI analysis across all signals...")
            analysis = None
            try:
                ai_raw = analyze_company(company_data=company_obj.model_dump(),
                    funding=funding, jobs=jobs, news=news,
                    techstack=techstack, github=github, financials=financials)
                analysis = parse_llm_result(ai_raw)
            except Exception as e:
                st.warning(f"AI analysis failed: {e}")
            result = {"company": company_obj.model_dump(), "analysis": analysis,
                      "funding": funding, "jobs": jobs, "news": news,
                      "techstack": techstack, "github": github, "financials": financials}
            if analysis:
                save_to_cache(clean_domain, result)
            status.update(label="Pipeline complete", state="complete", expanded=False)
        company = company_obj.model_dump()

    if not analysis:
        st.error("Analysis failed -- could not retrieve or parse data for this domain.")
        st.stop()

    scoring = apply_acquisition_scoring(
        company, analysis,
        preferred_sectors=[selected_sector], preferred_regions=[selected_region],
        preferred_maturity=[selected_maturity], weight_ai=weight_ai, weight_rules=weight_rules,
        funding=funding, jobs=jobs, news=news, techstack=techstack, github=github, financials=financials)

    ai_score         = scoring["ai_score"]
    rule_score       = scoring["rule_score"]
    final_score      = scoring["final_score"]
    confidence_pct   = scoring["confidence_pct"]
    confidence_label = scoring["confidence_label"]
    evidence_count   = scoring["evidence_count"]
    growth_score     = scoring["growth_score"]
    quality_score    = scoring["quality_score"]
    risk_score       = scoring["risk_score"]
    risks            = analysis.get("risk_flags", [])
    positives        = analysis.get("positive_signals", [])

    if final_score >= 8:
        score_color, verdict_cls, verdict_txt = "#3fb950", "v-strong", "Strong Candidate"
    elif final_score >= 5.5:
        score_color, verdict_cls, verdict_txt = "#e3b341", "v-moderate", "Moderate Fit"
    else:
        score_color, verdict_cls, verdict_txt = "#f85149", "v-weak", "Weak Fit"

    # Provenance banner
    sources = [
        ("AbstractAPI",   bool(company.get("name") and company.get("name") != clean_domain)),
        ("Website",       bool(company.get("raw_summary") and "No website" not in company.get("raw_summary",""))),
        ("News",          bool(news)),
        ("EDGAR/Funding", bool(funding)),
        ("Job Postings",  bool(jobs)),
        ("Tech Stack",    bool(techstack)),
        ("GitHub",        bool(github)),
        ("Financials",    bool(financials and financials.get("is_public"))),
    ]
    prov_html = '<div class="prov-banner">'
    for src, hit in sources:
        cls = "prov-hit" if hit else "prov-miss"
        ico = "+" if hit else "o"
        prov_html += f'<div class="prov-item {cls}">{ico} {src}</div>'
    prov_html += '</div>'
    st.markdown(prov_html, unsafe_allow_html=True)

    tab_overview, tab_analysis, tab_scoring, tab_evidence = st.tabs(["Overview", "Analysis", "Scoring", "Evidence"])

    # Tab 1: Overview
    with tab_overview:
        col_score, col_profile = st.columns([1, 2])
        with col_score:
            conf_col = {"High":"#3fb950","Medium":"#e3b341","Low":"#f85149"}.get(confidence_label,"#8b9eb0")
            st.markdown(
                f'<div class="card" style="text-align:center;">'
                f'<div class="section-title">Acquisition Score</div>'
                f'<div class="score-ring-wrap">'
                f'<div class="score-ring-num" style="color:{score_color};">{final_score:.1f}</div>'
                f'<div class="score-ring-lbl">out of 10</div></div>'
                f'<div><span class="verdict {verdict_cls}">{verdict_txt}</span></div>'
                f'<div style="margin-top:16px;display:flex;justify-content:center;gap:20px;">'
                f'<div style="text-align:center;"><div style="font-size:11px;color:#4a5568;text-transform:uppercase;letter-spacing:.08em;">Confidence</div>'
                f'<div style="font-size:18px;font-weight:700;color:{conf_col};">{confidence_pct}%</div>'
                f'<div style="font-size:11px;color:{conf_col};">{confidence_label}</div></div>'
                f'<div style="text-align:center;"><div style="font-size:11px;color:#4a5568;text-transform:uppercase;letter-spacing:.08em;">Signals</div>'
                f'<div style="font-size:18px;font-weight:700;color:#cdd9e5;">{evidence_count}</div>'
                f'<div style="font-size:11px;color:#4a5568;">analyzed</div></div>'
                f'</div>'
                f'<div style="margin-top:16px;">'
                + score_bar("AI Score",      ai_score,     10, "#4a90d9")
                + score_bar("Rule Score",    rule_score,   10, "#8b5cf6")
                + score_bar("Growth Score",  growth_score, 10, "#3fb950")
                + score_bar("Quality Score", quality_score,10, "#e3b341")
                + score_bar("Risk Score",    risk_score,   10, "#f85149")
                + '</div></div>', unsafe_allow_html=True)

            growth = analysis.get("growth_signal", "unknown")
            g_col  = GROWTH_C.get(growth, "#8b9eb0")
            tech   = analysis.get("tech_assessment", "unknown")
            t_col  = {"modern":"#3fb950","mixed":"#e3b341","legacy":"#f85149"}.get(tech, "#8b9eb0")
            st.markdown(
                f'<div class="card"><div class="section-title">Quick Signals</div>'
                f'<div class="profile-row"><span class="profile-key">Growth Signal</span>'
                f'<span class="profile-val" style="color:{g_col};font-weight:700;">{growth.title()}</span></div>'
                f'<div class="profile-row"><span class="profile-key">Tech Assessment</span>'
                f'<span class="profile-val" style="color:{t_col};font-weight:700;">{tech.title()}</span></div>'
                f'<div class="profile-row"><span class="profile-key">Sector</span>'
                f'<span class="profile-val">{analysis.get("sector_classification","--")}</span></div>'
                f'<div class="profile-row"><span class="profile-key">Stage</span>'
                f'<span class="profile-val">{analysis.get("maturity_stage","--")}</span></div>'
                f'</div>', unsafe_allow_html=True)

        with col_profile:
            emp = company.get("size_estimate") or (str(financials["employees"])+" (public)" if financials and financials.get("employees") else "--")
            rows_html = (
                f'<div class="profile-row"><span class="profile-key">Name</span><span class="profile-val">{company.get("name","--")}</span></div>'
                f'<div class="profile-row"><span class="profile-key">Website</span><span class="profile-val">'
                f'<a href="https://{company.get("website","")}" style="color:#4a90d9;" target="_blank">{company.get("website","--")}</a></span></div>'
                f'<div class="profile-row"><span class="profile-key">Industry</span><span class="profile-val">{company.get("industry") or analysis.get("sector_classification","--")}</span></div>'
                f'<div class="profile-row"><span class="profile-key">Location</span><span class="profile-val">{company.get("location","--")}</span></div>'
                f'<div class="profile-row"><span class="profile-key">Employees</span><span class="profile-val">{emp}</span></div>')
            if financials and financials.get("is_public"):
                mcap = financials.get("market_cap")
                mcap_str = fmt_usd(mcap)
                rows_html += (
                    f'<div class="profile-row"><span class="profile-key">Ticker</span>'
                    f'<span class="profile-val" style="color:#4a90d9;font-weight:700;">{financials.get("ticker")} ({financials.get("exchange","--")})</span></div>'
                    f'<div class="profile-row"><span class="profile-key">Market Cap</span><span class="profile-val">{mcap_str}</span></div>')
            st.markdown(f'<div class="card"><div class="section-title">Company Profile</div>{rows_html}</div>', unsafe_allow_html=True)
            summary = analysis.get("summary","")
            if summary:
                st.markdown(f'<div class="card"><div class="section-title">Executive Summary</div><div class="narrative-block">{summary}</div></div>', unsafe_allow_html=True)

        col_r, col_p = st.columns(2)
        with col_r:
            st.markdown('<div class="section-title">Risk Flags</div>', unsafe_allow_html=True)
            pills = "".join(f'<div class="risk-pill">! {r}</div>' for r in risks) if risks else '<div style="color:#4a5568;">None identified.</div>'
            st.markdown(f'<div>{pills}</div>', unsafe_allow_html=True)
        with col_p:
            st.markdown('<div class="section-title">Positive Signals</div>', unsafe_allow_html=True)
            pills = "".join(f'<div class="pos-pill">+ {p}</div>' for p in positives) if positives else '<div style="color:#4a5568;">None identified.</div>'
            st.markdown(f'<div>{pills}</div>', unsafe_allow_html=True)

    # Tab 2: Analysis
    with tab_analysis:
        # Metric cards row
        m1, m2, m3, m4, m5, m6 = st.columns(6)
        m1.metric("Fit Score",     f"{final_score}/10", delta=f"{final_score - 5:.1f} vs mid")
        m2.metric("Confidence",    f"{confidence_pct}%")
        m3.metric("Growth Score",  f"{growth_score}/10")
        m4.metric("Quality Score", f"{quality_score}/10")
        m5.metric("Risk Score",    f"{risk_score}/10")
        m6.metric("Signals",       evidence_count)

        # Second row: funding + news counts
        f1, f2, f3, f4 = st.columns(4)
        total_raised = (funding or {}).get("total_funding_usd") or 0
        f1.metric("Total Raised", fmt_usd(total_raised) if total_raised else "Unknown")
        months_since = (funding or {}).get("months_since_raise")
        f2.metric("Last Raise", f"{months_since}mo ago" if months_since else "--")
        art_count = len((news or {}).get("articles", []))
        f3.metric("News Articles", art_count)
        f4.metric("Risk Flags", len(risks))

        # Narrative sections
        SECTIONS = [("funding_outlook","Funding Outlook"),("hiring_health","Hiring Health"),
                    ("tech_maturity","Tech Maturity"),("market_position","Market Position"),("reasoning","Scoring Rationale")]
        col_a1, col_a2 = st.columns(2)
        for idx, (key, label) in enumerate(SECTIONS):
            text = analysis.get(key,"")
            if not text: continue
            with (col_a1 if idx % 2 == 0 else col_a2):
                st.markdown(f'<div class="card"><div class="narrative-label">{label}</div><div class="narrative-block">{text}</div></div>', unsafe_allow_html=True)

    # Tab 3: Scoring
    with tab_scoring:
        col_s1, col_s2 = st.columns([1, 2])
        with col_s1:
            conf_col2 = {"High":"#3fb950","Medium":"#e3b341","Low":"#f85149"}.get(confidence_label,"#8b9eb0")
            st.markdown(
                f'<div class="card"><div class="section-title">Score Composition</div>'
                f'<div class="profile-row"><span class="profile-key">Final Score</span><span class="profile-val" style="color:{score_color};font-weight:800;font-size:20px;">{final_score} / 10</span></div>'
                f'<div class="profile-row"><span class="profile-key">Confidence</span><span class="profile-val" style="color:{conf_col2};font-weight:700;">{confidence_pct}% ({confidence_label})</span></div>'
                f'<div class="profile-row"><span class="profile-key">Signals Analyzed</span><span class="profile-val">{evidence_count}</span></div>'
                f'<div class="profile-row"><span class="profile-key">AI Score</span><span class="profile-val" style="color:#4a90d9;font-weight:700;">{ai_score} / 10</span></div>'
                f'<div class="profile-row"><span class="profile-key">Rule Score</span><span class="profile-val" style="color:#8b5cf6;font-weight:700;">{rule_score} / 10</span></div>'
                f'<div class="profile-row"><span class="profile-key">Growth Score</span><span class="profile-val" style="color:#3fb950;font-weight:700;">{growth_score} / 10</span></div>'
                f'<div class="profile-row"><span class="profile-key">Quality Score</span><span class="profile-val" style="color:#e3b341;font-weight:700;">{quality_score} / 10</span></div>'
                f'<div class="profile-row"><span class="profile-key">Risk Score</span><span class="profile-val" style="color:#f85149;font-weight:700;">{risk_score} / 10</span></div>'
                f'</div>', unsafe_allow_html=True)
        with col_s2:
            adjustments = scoring.get("adjustments", [])
            groups_order = ["Thesis","Funding","Hiring","Tech","GitHub","Financials","News","Risk"]
            by_group = {}
            for adj in adjustments:
                by_group.setdefault(adj.get("group","Other"), []).append(adj)
            for grp in groups_order:
                adjs = by_group.get(grp)
                if not adjs: continue
                rows = ""
                for adj in adjs:
                    pts = adj["pts"]
                    val_cls = "adj-val-pos" if pts > 0 else ("adj-val-neg" if pts < 0 else "adj-val-neu")
                    pts_str = f"+{pts}" if pts > 0 else str(pts)
                    rows += (f'<div class="adj-row"><span class="adj-lbl"><span class="adj-group">{grp}</span>{adj["label"]}</span>'
                             f'<span class="{val_cls}">{pts_str}</span></div>')
                st.markdown(f'<div class="card">{rows}</div>', unsafe_allow_html=True)

        # Risk flags in scoring tab
        if risks:
            st.markdown('<div class="section-title" style="margin-top:8px;">Risk Flags</div>', unsafe_allow_html=True)
            pills_r = "".join(f'<div class="risk-pill">! {r}</div>' for r in risks)
            st.markdown(f'<div class="card">{pills_r}</div>', unsafe_allow_html=True)
        if positives:
            st.markdown('<div class="section-title" style="margin-top:8px;">Positive Signals</div>', unsafe_allow_html=True)
            pills_p = "".join(f'<div class="pos-pill">+ {p}</div>' for p in positives)
            st.markdown(f'<div class="card">{pills_p}</div>', unsafe_allow_html=True)

    # Tab 4: Evidence
    with tab_evidence:
        col_e1, col_e2 = st.columns([1.3, 1])
        with col_e1:
            st.markdown('<div class="section-title">Recent News</div>', unsafe_allow_html=True)
            if news and news.get("articles"):
                na = news.get("analysis") or {}
                ns = na.get("overall_news_score")
                gs = na.get("growth_signal")
                rs = na.get("risk_signal")

                # Score row
                m_n1, m_n2, m_n3 = st.columns(3)
                m_n1.metric("News Score",     f"{ns:.1f}/10" if ns is not None else "--")
                m_n2.metric("Growth Signal",  f"{gs:.1f}/10" if gs is not None else "--")
                m_n3.metric("Risk Signal",    f"{rs:.1f}/10" if rs is not None else "--")

                if na.get("summary"):
                    st.markdown(f'<div class="card" style="margin-bottom:12px;"><div class="narrative-block">{na["summary"]}</div></div>', unsafe_allow_html=True)

                CAT_C = {
                    "funding":"#4a90d9","acquisition":"#8b5cf6","partnership":"#3fb950",
                    "product_launch":"#3fb950","hiring":"#3fb950","layoffs":"#f85149",
                    "lawsuit":"#f85149","breach":"#f85149","executive":"#e3b341","general_mention":"#4a5568",
                }

                def _sentiment_bar(val):
                    if val is None: return ""
                    pct = int((val + 1) / 2 * 100)
                    col = "#3fb950" if val > 0.2 else ("#f85149" if val < -0.2 else "#e3b341")
                    return (f'<div style="display:flex;align-items:center;gap:8px;margin-top:4px;">'
                            f'<div style="flex:1;height:4px;background:#1e2530;border-radius:2px;">'
                            f'<div style="width:{pct}%;height:100%;background:{col};border-radius:2px;"></div></div>'
                            f'<span style="font-size:11px;color:{col};font-weight:700;white-space:nowrap;">{val:+.2f}</span></div>')

                arts_html = ""
                for a in news["articles"]:
                    url   = a.get("url","")
                    title = a.get("title","") or ""
                    title_link = f'<a href="{url}" target="_blank" style="color:#cdd9e5;text-decoration:none;">{title}</a>' if url else title
                    cat   = a.get("category","general_mention")
                    cat_c = CAT_C.get(cat, "#4a5568")
                    cat_badge = f'<span style="background:{cat_c}22;color:{cat_c};border:1px solid {cat_c}44;border-radius:3px;padding:1px 7px;font-size:11px;font-weight:700;text-transform:uppercase;margin-right:8px;">{cat.replace("_"," ")}</span>'
                    sent  = a.get("sentiment")
                    bi    = a.get("business_impact")
                    conf  = a.get("confidence")
                    desc  = a.get("description") or ""

                    meta  = f'<div class="news-meta">{a.get("source","")} &middot; {a.get("published_at","")}'
                    if conf is not None:
                        meta += f' &middot; <span style="color:#4a5568;">confidence {conf:.0%}</span>'
                    meta += '</div>'

                    desc_html = f'<div class="news-desc">{desc[:200]}{"..." if len(desc)>200 else ""}</div>' if desc else ""

                    scores_html = ""
                    if sent is not None:
                        scores_html += f'<div style="font-size:12px;color:#4a5568;margin-top:6px;">Sentiment{_sentiment_bar(sent)}</div>'
                    if bi is not None:
                        scores_html += f'<div style="font-size:12px;color:#4a5568;margin-top:4px;">Business impact{_sentiment_bar(bi)}</div>'

                    signals = a.get("signals",[])
                    risks   = a.get("risk_flags",[])
                    sig_html = ""
                    if signals:
                        sig_html += '<div style="margin-top:6px;">' + "".join(
                            f'<span style="background:#3fb95015;color:#3fb950;border:1px solid #3fb95030;border-radius:3px;padding:1px 8px;font-size:11px;margin:2px 3px 2px 0;display:inline-block;">+ {s}</span>'
                            for s in signals) + '</div>'
                    if risks:
                        sig_html += '<div style="margin-top:4px;">' + "".join(
                            f'<span style="background:#f8514915;color:#f85149;border:1px solid #f8514930;border-radius:3px;padding:1px 8px;font-size:11px;margin:2px 3px 2px 0;display:inline-block;">! {r}</span>'
                            for r in risks) + '</div>'

                    arts_html += (f'<div class="news-item">{cat_badge}{title_link}{meta}'
                                  f'{desc_html}{scores_html}{sig_html}</div>')

                st.markdown(f'<div class="card">{arts_html}</div>', unsafe_allow_html=True)
            else:
                st.markdown('<div class="card"><div style="color:#4a5568;">No news coverage found.</div></div>', unsafe_allow_html=True)

        with col_e2:
            st.markdown('<div class="section-title">Job Postings</div>', unsafe_allow_html=True)
            if jobs:
                ats_html = f'<div style="font-size:13px;color:#4a90d9;margin-bottom:10px;">ATS: <b>{jobs["ats_detected"]}</b></div>' if jobs.get("ats_detected") else ""
                fn_rows = "".join(f'<div class="profile-row"><span class="profile-key">{fn}</span><span class="profile-val" style="color:#4a90d9;">Hiring</span></div>' for fn in (jobs.get("top_functions") or []))
                locs = ", ".join(jobs.get("top_locations",[])[:3]) or "Not specified"
                sample_listings = jobs.get("sample_listings") or []
                if sample_listings:
                    listings_html = "".join(
                        f'<div style="padding:7px 0;border-bottom:1px solid #1e2530;">' +
                        (f'<a href="{l["url"]}" target="_blank" style="color:#cdd9e5;font-size:14px;text-decoration:none;">' + l["title"] + '</a>' if l.get("url") else f'<span style="font-size:14px;color:#cdd9e5;">{l["title"]}</span>') +
                        (f'<div style="font-size:12px;color:#4a5568;">{l["location"]}</div>' if l.get("location") else "") +
                        '</div>'
                        for l in sample_listings
                    )
                    samples_section = f'<div style="margin-top:14px;"><div class="evidence-header">Sample Listings</div>{listings_html}</div>'
                else:
                    plain = "".join(f'<div style="padding:6px 0;border-bottom:1px solid #1e2530;font-size:14px;color:#cdd9e5;">{t}</div>' for t in (jobs.get("sample_titles") or []))
                    samples_section = f'<div style="margin-top:14px;"><div class="evidence-header">Sample Titles</div>{plain}</div>' if plain else ""
                st.markdown(
                    f'<div class="card"><div style="font-size:36px;font-weight:800;color:#4a90d9;">{jobs["posting_count"]}</div>'
                    f'<div style="font-size:13px;color:#4a5568;text-transform:uppercase;letter-spacing:.08em;margin-bottom:14px;">Active Postings</div>'
                    f'{ats_html}<div style="font-size:13px;color:#8b9eb0;margin-bottom:10px;">{locs}</div>'
                    f'{fn_rows}{samples_section}</div>',
                    unsafe_allow_html=True)
            else:
                st.markdown('<div class="card"><div style="color:#4a5568;">No job postings found.</div></div>', unsafe_allow_html=True)

        col_e3, col_e4 = st.columns(2)
        with col_e3:
            st.markdown('<div class="section-title" style="margin-top:8px;">Tech Stack</div>', unsafe_allow_html=True)
            if techstack:
                ENG_C = {"modern":"#3fb950","mixed":"#e3b341","legacy":"#f85149"}
                sig_col = ENG_C.get(techstack.get("stack_signal",""), "#8b9eb0")
                cat_html = "".join(f'<div class="profile-row"><span class="profile-key">{cat}</span><span class="profile-val" style="font-size:13px;">{", ".join(techs[:5])}</span></div>' for cat, techs in techstack.get("categories",{}).items())
                modern = techstack.get("modern_techs",[])
                legacy = techstack.get("legacy_techs",[])
                m_html = '<div style="margin-top:12px;"><div class="evidence-header">Modern</div>' + "".join(f'<span class="tag" style="color:#3fb950;">{t}</span>' for t in modern) + '</div>' if modern else ""
                l_html = '<div style="margin-top:10px;"><div class="evidence-header">Legacy</div>' + "".join(f'<span class="tag" style="color:#f85149;">{t}</span>' for t in legacy) + '</div>' if legacy else ""
                st.markdown(
                    '<div class="card"><div style="margin-bottom:14px;">'
                    + pill(techstack.get("stack_signal","unknown")+" stack", sig_col)
                    + f'<span style="font-size:13px;color:#4a5568;margin-left:10px;">{techstack.get("total_detected",0)} technologies</span></div>'
                    + f'{cat_html}{m_html}{l_html}</div>', unsafe_allow_html=True)
            else:
                st.markdown('<div class="card"><div style="color:#4a5568;">Tech stack detection runs from HTML. May fail if site blocked scraping.</div></div>', unsafe_allow_html=True)

        with col_e4:
            st.markdown('<div class="section-title" style="margin-top:8px;">GitHub Engineering</div>', unsafe_allow_html=True)
            if github:
                EC = {"strong":"#3fb950","moderate":"#e3b341","light":"#8b9eb0","none":"#4a5568"}
                ec = EC.get(github.get("eng_signal","none"), "#8b9eb0")
                langs = ", ".join(github.get("top_languages",[])) or "--"
                gh_rows = (
                    f'<div class="profile-row"><span class="profile-key">Org</span><span class="profile-val"><a href="{github["github_url"]}" style="color:#4a90d9;">@{github["org_login"]}</a></span></div>'
                    f'<div class="profile-row"><span class="profile-key">Public Repos</span><span class="profile-val">{github.get("public_repos",0)}</span></div>'
                    f'<div class="profile-row"><span class="profile-key">Total Stars</span><span class="profile-val">{github.get("total_stars",0):,}</span></div>'
                    f'<div class="profile-row"><span class="profile-key">Commits (90d)</span><span class="profile-val">{github.get("recent_commits",0)}</span></div>'
                    f'<div class="profile-row"><span class="profile-key">Top Languages</span><span class="profile-val" style="font-size:13px;">{langs}</span></div>'
                    f'<div class="profile-row"><span class="profile-key">Eng Signal</span><span class="profile-val" style="color:{ec};font-weight:700;">{github.get("eng_signal","--").title()}</span></div>')
                st.markdown('<div class="card"><div style="margin-bottom:14px;">' + pill(github.get("eng_signal","unknown")+" engineering", ec) + '</div>' + gh_rows + '</div>', unsafe_allow_html=True)
            else:
                st.markdown('<div class="card"><div style="color:#4a5568;">No GitHub org found. Add GITHUB_TOKEN (no scopes) to increase rate limit.</div></div>', unsafe_allow_html=True)

        # Financials panel
        st.markdown('<div class="section-title" style="margin-top:8px;">Public Market Financials</div>', unsafe_allow_html=True)
        if financials and financials.get("is_public"):
            rev_growth = financials.get("revenue_growth")
            op_margin  = financials.get("operating_margin")
            rg_col = "#3fb950" if (rev_growth or 0) >= 0.10 else ("#e3b341" if (rev_growth or 0) >= 0 else "#f85149")
            om_col = "#3fb950" if (op_margin or 0) >= 0.10 else ("#e3b341" if (op_margin or 0) >= 0 else "#f85149")
            ar = (financials.get("analyst_recommendation") or "--").upper()
            ar_col = {"BUY":"#3fb950","STRONG BUY":"#3fb950","HOLD":"#e3b341","SELL":"#f85149","STRONG SELL":"#f85149"}.get(ar,"#8b9eb0")
            fc1, fc2, fc3 = st.columns(3)
            with fc1:
                st.markdown(
                    f'<div class="card"><div class="section-title">Valuation</div>'
                    f'<div class="profile-row"><span class="profile-key">Ticker</span><span class="profile-val" style="color:#4a90d9;font-weight:700;">{financials.get("ticker")} ({financials.get("exchange","--")})</span></div>'
                    f'<div class="profile-row"><span class="profile-key">Market Cap</span><span class="profile-val">{fmt_usd(financials.get("market_cap"))}</span></div>'
                    f'<div class="profile-row"><span class="profile-key">EV / Revenue</span><span class="profile-val">{fmt_x(financials.get("ev_revenue"))}</span></div>'
                    f'<div class="profile-row"><span class="profile-key">EV / EBITDA</span><span class="profile-val">{fmt_x(financials.get("ev_ebitda"))}</span></div>'
                    f'<div class="profile-row"><span class="profile-key">P/E Ratio</span><span class="profile-val">{fmt_x(financials.get("pe_ratio"))}</span></div>'
                    f'</div>', unsafe_allow_html=True)
            with fc2:
                de = financials.get("debt_equity")
                de_str = "--" if de is None else str(round(de,2))
                st.markdown(
                    f'<div class="card"><div class="section-title">Financials (TTM)</div>'
                    f'<div class="profile-row"><span class="profile-key">Revenue</span><span class="profile-val">{fmt_usd(financials.get("revenue_ttm"))}</span></div>'
                    f'<div class="profile-row"><span class="profile-key">Revenue Growth</span><span class="profile-val" style="color:{rg_col};font-weight:700;">{fmt_pct(rev_growth)}</span></div>'
                    f'<div class="profile-row"><span class="profile-key">Operating Margin</span><span class="profile-val" style="color:{om_col};font-weight:700;">{fmt_pct(op_margin)}</span></div>'
                    f'<div class="profile-row"><span class="profile-key">Net Margin</span><span class="profile-val">{fmt_pct(financials.get("net_margin"))}</span></div>'
                    f'<div class="profile-row"><span class="profile-key">Cash</span><span class="profile-val">{fmt_usd(financials.get("cash"))}</span></div>'
                    f'<div class="profile-row"><span class="profile-key">Debt / Equity</span><span class="profile-val">{de_str}</span></div>'
                    f'</div>', unsafe_allow_html=True)
            with fc3:
                upside = financials.get("analyst_upside_pct")
                u_str = ("%+.1f%%" % upside) if upside is not None else "--"
                u_col = "#3fb950" if (upside or 0) > 10 else ("#e3b341" if (upside or 0) > 0 else "#f85149")
                lo = financials.get("price_52w_low"); hi = financials.get("price_52w_high")
                range_str = ("$%.2f - $%.2f" % (lo, hi)) if lo else "--"
                pfl = financials.get("pct_from_52w_low")
                pfl_str = ("+%.1f%% from low" % pfl) if pfl is not None else ""
                tp = financials.get("target_price")
                tp_str = ("$%.2f" % tp) if tp else "--"
                emp = financials.get("employees")
                emp_str = ("%s" % f"{emp:,}") if emp else "--"
                st.markdown(
                    f'<div class="card"><div class="section-title">Market &amp; Analysts</div>'
                    f'<div class="profile-row"><span class="profile-key">Price</span><span class="profile-val">${financials["price"]:.2f} {financials.get("currency","USD")}</span></div>'
                    f'<div class="profile-row"><span class="profile-key">52-Week Range</span><span class="profile-val" style="font-size:13px;">{range_str} <span style="color:#4a5568;">{pfl_str}</span></span></div>'
                    f'<div class="profile-row"><span class="profile-key">Analyst Target</span><span class="profile-val">{tp_str} <span style="color:{u_col};font-weight:700;">{u_str}</span></span></div>'
                    f'<div class="profile-row"><span class="profile-key">Analyst Rating</span><span class="profile-val" style="color:{ar_col};font-weight:700;">{ar}</span></div>'
                    f'<div class="profile-row"><span class="profile-key">Employees</span><span class="profile-val">{emp_str}</span></div>'
                    f'</div>', unsafe_allow_html=True)
        else:
            st.markdown('<div class="card"><div style="color:#4a5568;">Private company — no public financial data available.</div></div>', unsafe_allow_html=True)
