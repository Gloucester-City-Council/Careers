#!/usr/bin/env python3
"""
Scrape job listings from the Gloucester City/County Council careers page
(SAP SuccessFactors Recruiting Marketing / Lumesse TalentLink)
and write jobs-feed.xml in the format expected by jobs/index.html.

Usage:
    python3 scrape_jobs.py <input.html> <output.xml>
"""

import sys
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

try:
    from bs4 import BeautifulSoup
except ImportError:
    import subprocess
    subprocess.run(
        [sys.executable, '-m', 'pip', 'install', '--quiet', 'beautifulsoup4', 'lxml'],
        check=True
    )
    from bs4 import BeautifulSoup

# ── Args ──────────────────────────────────────────────────────────────────────
INPUT_HTML  = sys.argv[1] if len(sys.argv) > 1 else '/tmp/jobs-page.html'
OUTPUT_XML  = sys.argv[2] if len(sys.argv) > 2 else '/tmp/jobs-feed-new.xml'
BASE_URL    = 'https://careers.gloucestershire.gov.uk'

with open(INPUT_HTML, encoding='utf-8', errors='replace') as fh:
    html = fh.read()

soup = BeautifulSoup(html, 'html.parser')

# ── Debug: list every element that has a job/vacancy-related class or id ──────
print('=== Job-related elements found in page ===', flush=True)
seen: set = set()
for el in soup.find_all(True):
    classes = ' '.join(el.get('class', []))
    eid     = el.get('id', '')
    if any(k in classes.lower() or k in eid.lower()
           for k in ('job', 'vacanc', 'listing', 'result', 'position', 'role', 'vacancy')):
        sig = f'{el.name}|{classes}|{eid}'
        if sig not in seen:
            seen.add(sig)
            print(f'  <{el.name:8s} class="{classes}"  id="{eid}">')
print('=== End of job-related elements ===\n', flush=True)

# ── Try progressively broader selectors to find job items ─────────────────────
SELECTORS = [
    # SAP RMK / TalentLink common patterns (most specific first)
    'li.job-list-item',
    'li.list-job-result',
    'li.jobResult',
    'div.listingItem',
    'div.listing-item',
    'div.job-listing',
    'div.job-result',
    'tr.listing-result',
    '.search-result-item',
    '[class*="job-result"]',
    '[class*="jobResult"]',
    '[class*="vacancy-item"]',
    '[class*="vacancyItem"]',
    # broader fallbacks
    '#job-search-results li',
    '#jobList li',
    '#job-results li',
    '#jobs li',
    '.jobs-list li',
    '.job-listings li',
    'ul[id*="job"] li',
    'ul[class*="job"] li',
    'div[id*="result"] li',
    'div[class*="result"] li',
]

job_items = []
for sel in SELECTORS:
    items = soup.select(sel)
    if items:
        print(f'Matched selector: {sel!r} → {len(items)} item(s)', flush=True)
        job_items = items
        break

if not job_items:
    print('WARNING: No job items found with known selectors.', file=sys.stderr)
    print('Printing first 5000 chars of <body> for debugging:', file=sys.stderr)
    body = soup.find('body')
    if body:
        print(str(body)[:5000], file=sys.stderr)
    # Write empty but valid XML so the workflow can detect the issue gracefully
    root = ET.Element('jobs')
    tree = ET.ElementTree(root)
    with open(OUTPUT_XML, 'w', encoding='utf-8') as fh:
        fh.write('<?xml version="1.0" encoding="UTF-8" ?>\n<jobs>\n</jobs>\n')
    print('Written empty jobs feed.', flush=True)
    sys.exit(0)

# ── Helper: get text from first matching selector ─────────────────────────────
def get_text(el, *selectors, default=''):
    for sel in selectors:
        found = el.select_one(sel)
        if found:
            return found.get_text(' ', strip=True)
    # Fallback: search by common text patterns in all text nodes
    return default

def get_href(el, *selectors, default=''):
    for sel in selectors:
        found = el.select_one(sel)
        if found and found.get('href'):
            href = found['href'].strip()
            if href.startswith('/'):
                href = BASE_URL + href
            return href
    return default

# ── Parse each job item ───────────────────────────────────────────────────────
now_str = datetime.now(timezone.utc).strftime('%a, %d %m %Y 00:00:00 GMT')
jobs = []

for item in job_items:
    item_html = str(item)[:300].replace('\n', ' ')
    print(f'\n--- Item HTML preview: {item_html!r}', flush=True)

    title = get_text(item,
        '.job-name a', '.job-title a', '.jobTitle a',
        'h2 a', 'h3 a', 'h4 a',
        'a.job-title', 'a.title',
        '.job-name', '.job-title', '.jobTitle',
        'h2', 'h3', 'h4',
        default='')

    apply_url = get_href(item,
        '.job-name a', '.job-title a', '.jobTitle a',
        'h2 a', 'h3 a', 'h4 a',
        'a.job-title', 'a.title', 'a.btn-apply', 'a.apply',
        'a',
        default='')

    location = get_text(item,
        '.job-location', '.location', '[class*="location"]',
        '.job-town', '[class*="town"]',
        '.job-city', '[class*="city"]',
        default='Gloucester')

    closing = get_text(item,
        '.expiry-date', '.closing-date', '[class*="closing"]',
        '.expiry', '[class*="expiry"]',
        '.deadline', '[class*="deadline"]',
        default='')

    tenure = get_text(item,
        '.job-type', '.contract-type', '[class*="type"]',
        '.employment-type', '[class*="employment"]',
        '.tenure', '[class*="tenure"]',
        default='Permanent')

    salary = get_text(item,
        '.job-salary', '.salary', '[class*="salary"]',
        '.remuneration', '[class*="remuneration"]',
        '.pay', '[class*="pay"]',
        default='')

    if not title and not apply_url:
        print('  (skipped — no title or URL found)', flush=True)
        continue

    # Extract numeric job ID from URL
    job_id = ''
    if apply_url:
        m = re.search(r'/(\d+)/?(?:\?.*)?$', apply_url)
        if m:
            job_id = m.group(1)

    # Build a description HTML blob with salary + hours (as expected by index.html)
    desc_items = []
    if salary:
        desc_items.append(f'Salary: {salary}')
    desc_html = '<ul>' + ''.join(f'<li>{d}</li>' for d in desc_items) + '</ul>' if desc_items else ''

    print(f'  → id={job_id!r} title={title!r} location={location!r} closing={closing!r}', flush=True)

    jobs.append({
        'externalid':   job_id,
        'jobtitle':     title,
        'locationcity': location or 'Gloucester',
        'jobtenure':    tenure or 'Permanent',
        'type':         closing,      # closing date field mapped to <type> per index.html
        'date':         now_str,
        'applyURL':     apply_url,
        'description':  desc_html,
    })

print(f'\n=== Total jobs extracted: {len(jobs)} ===', flush=True)

# ── Generate XML ──────────────────────────────────────────────────────────────
root = ET.Element('jobs')
for j in jobs:
    job_el = ET.SubElement(root, 'job')
    for tag, val in j.items():
        child = ET.SubElement(job_el, tag)
        child.text = val or ''

# Serialise with pretty-print
from xml.dom import minidom
raw_xml = ET.tostring(root, encoding='unicode')
dom     = minidom.parseString(raw_xml)
pretty  = dom.toprettyxml(indent='  ', encoding=None)
# minidom adds its own declaration; replace with ours
pretty  = re.sub(r'^<\?xml[^?]*\?>\n?', '', pretty)
output  = '<?xml version="1.0" encoding="UTF-8" ?>\n' + pretty

with open(OUTPUT_XML, 'w', encoding='utf-8') as fh:
    fh.write(output)

print(f'Written {len(jobs)} job(s) to {OUTPUT_XML}', flush=True)
