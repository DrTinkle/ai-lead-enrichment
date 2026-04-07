# AI-Powered Lead / Company Enrichment Tool

### Live Demo

A live version of the application is available at:  
[https://ai-lead-enrichment.streamlit.app/](https://ai-lead-enrichment.streamlit.app/)

## Overview

This project is a Python-based lead enrichment and acquisition screening tool.

It takes a company domain as input, gathers publicly available signals, enriches the data using an LLM, and evaluates the company against a configurable acquisition thesis.

The result is a structured analysis including:

- Company overview  
- AI-generated summary and classification  
- Deterministic rule-based scoring  
- Weighted blended final score  
- Transparent scoring breakdown  

The goal is to simulate a lightweight acquisition evaluation engine.

---

## Problem Statement

Acquisition teams often evaluate companies using a mix of:

- Public company information  
- Strategic alignment  
- Growth indicators  
- Risk signals  
- Internal investment thesis  

This project demonstrates how such a workflow can be partially automated using:

- API integrations  
- Web scraping  
- LLM-based analysis  
- Rule-based scoring logic  
- Weighted decision modeling  

---

## Architecture

### 1. Data Collection Layer

- Domain normalization  
- Optional enrichment via AbstractAPI  
- Website scraping (homepage + common company pages)  
- HTML parsing with BeautifulSoup  
- Text cleaning and truncation  

### 2. AI Enrichment Layer

Uses OpenAI to generate structured company analysis.

The LLM returns strict JSON containing:

- `summary`
- `sector_classification`
- `maturity_stage`
- `acquisition_fit_score`
- `risk_flags`
- `reasoning`

The system enforces JSON-only responses.

### 3. Scoring Engine

The tool uses a **blended weighted model**.

Two independent signals are calculated:

1. **AI Score** (0–10)  
2. **Rule Score** (0–10, thesis alignment)

Rule score considers:

- Sector match (+3)
- Region match (+2)
- Maturity match (+2)
- Risk penalties (−1 per risk, max −3)

Final score is calculated as:
Final Score = (AI Score × weight_ai) + (Rule Score × weight_rules)

### Default Weights

weight_ai = 0.6  
weight_rules = 0.4  

The UI displays:

- AI Score  
- Rule Score  
- Final Score  
- Full weighted formula breakdown  
- Rule adjustment explanations  

### Running Locally

Install dependencies:

pip install -r requirements.txt  

Run the app:

streamlit run streamlit_app.py  

---

### Environment Variables

OPENAI_API_KEY=your_key_here  
ABSTRACT_API_KEY=your_key_here (optional)  

---

### Deployment

Deployed on Railway as a Python service running Streamlit.

---

### Technical Highlights

- Python 3.11+  
- Pydantic schema validation  
- OpenAI structured JSON responses  
- Weighted blended scoring engine  
- Deterministic rule-based adjustments  
- API cost control via caching  
- Modular architecture  

---

### Limitations

- Depends on website content quality  
- AI output may vary slightly  
- Rule scoring uses deterministic matching  
- File-based cache is not persistent on ephemeral hosts  

---

### Future Improvements

- SQLite persistence layer  
- Adjustable scoring weights in UI  
- Batch CSV processing  
- Export results to CSV  
- Multi-company comparison view  
- Risk severity weighting  
- Authentication layer  

---

### Purpose

This project demonstrates:

- API integration  
- Data structuring  
- Practical LLM usage  
- Rule-based scoring logic  
- Business-aware automation  

- Clean modular architecture  
