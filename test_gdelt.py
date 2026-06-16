"""
Test GDELT news relevance for a company.
Usage: python test_gdelt.py <company_name> <domain>
Example: python test_gdelt.py Stripe stripe.com
"""
import sys, requests

GDELT_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
HEADERS   = {"User-Agent": "Mozilla/5.0 (compatible; lead-enrichment/0.1)"}

company = sys.argv[1] if len(sys.argv) > 1 else "Stripe"
domain  = sys.argv[2] if len(sys.argv) > 2 else "stripe.com"
root    = domain.split(".")[0].lower()
name    = company.lower()

def fetch(q, label):
    params = {"query": q, "mode": "artlist", "maxrecords": 25, "format": "json", "sort": "DateDesc"}
    r = requests.get(GDELT_URL, params=params, headers=HEADERS, timeout=15)
    print(f"\n=== {label} ===")
    print(f"Status: {r.status_code}  URL: {r.request.url[:120]}")
    if r.status_code != 200:
        print(r.text[:300]); return []
    arts = r.json().get("articles", [])
    print(f"Raw results: {len(arts)}")
    return arts

def score(a):
    title = (a.get("title") or "").lower()
    url   = (a.get("url") or "").lower()
    src   = (a.get("domain") or "").lower()
    s = 0
    if name in title:            s += 10
    if root in title and root != name: s += 6
    if name in url or root in url:     s += 3
    if name in src or root in src:     s += 1
    if not any(c.isascii() and c.isalpha() for c in title): s -= 5
    return s

for q, label in [
    (f"{company} {domain} sourcelang:english", "Pass 1: name + domain"),
    (f"{company} sourcelang:english",           "Pass 2: name only"),
]:
    arts = fetch(q, label)
    scored = sorted([(a, score(a)) for a in arts if a.get("title")], key=lambda x: -x[1])
    relevant = [a for a,s in scored if s >= 5]
    print(f"Relevant (score>=5): {len(relevant)}")
    for a, s in scored[:10]:
        flag = "OK" if s >= 5 else "--"
        print(f"  [{flag}] score={s:+d}  {a.get('title','')[:80]}")
