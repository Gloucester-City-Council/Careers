#!/usr/bin/env python3
"""
Scrape job listings from the Gloucester City/County Council careers page
(SAP SuccessFactors / Lumesse TalentLink — table#searchresults layout)
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
INPUT_HTML = sys.argv[1] if len(sys.argv) > 1 else '/tmp/jobs-page.html'
OUTPUT_XML = sys.argv[2] if len(sys.argv) > 2 else '/tmp/jobs-feed-new.xml'
BASE_URL   = 'https://careers.gloucestershire.gov.uk'

with open(INPUT_HTML, encoding='utf-8', errors='replace') as fh:
    html = fh.read()

soup = BeautifulSoup(html, 'html.parser')

# ── Find the results table ────────────────────────────────────────────────────
table = soup.select_one('table#searchresults')
if not table:
    print('ERROR: could not find table#searchresults in the page', file=sys.stderr)
    print('Page title:', soup.title.get_text() if soup.title else '(none)', file=sys.stderr)
    with open(OUTPUT_XML, 'w', encoding='utf-8') as fh:
        fh.write('<?xml version="1.0" encoding="UTF-8" ?>\n<jobs>\n</jobs>\n')
    sys.exit(1)

# Skip the header and filter rows (identified by known ids)
SKIP_IDS = {'search-results-header', 'search-results-filter'}
rows = [
    tr for tr in table.find_all('tr')
    if tr.get('id', '') not in SKIP_IDS
]
print(f'Found {len(rows)} data row(s) in table#searchresults', flush=True)

# ── Helper ────────────────────────────────────────────────────────────────────
def text(el, selector, default=''):
    """Return stripped text of first match, or default."""
    found = el.select_one(selector) if el else None
    return found.get_text(' ', strip=True) if found else default

def href(el, selector, default=''):
    """Return href of first match (made absolute), or default."""
    found = el.select_one(selector) if el else None
    if found and found.get('href'):
        h = found['href'].strip()
        return BASE_URL + h if h.startswith('/') else h
    return default

# ── Parse each row ────────────────────────────────────────────────────────────
now_str = datetime.now(timezone.utc).strftime('%a, %d %m %Y 00:00:00 GMT')
jobs = []

for row in rows:
    # Desktop layout uses hidden-phone spans; mobile uses visible-phone.
    # Prefer hidden-phone (desktop) spans, fall back to any match.
    title = (
        text(row, 'span.jobTitle.hidden-phone a')
        or text(row, 'a.jobTitle-link')
        or text(row, 'span.jobTitle a')
        or text(row, 'span.jobTitle')
    )
    apply_url = (
        href(row, 'span.jobTitle.hidden-phone a')
        or href(row, 'a.jobTitle-link')
        or href(row, 'span.jobTitle a')
        or href(row, 'a')
    )
    location = (
        text(row, 'span.jobLocation.hidden-phone')
        or text(row, 'span.jobLocation')
        or 'Gloucester'
    )
    department = (
        text(row, 'span.jobFacility.hidden-phone')
        or text(row, 'span.jobFacility')
        or text(row, 'span.jobDepartment')
        or ''
    )
    shift = (
        text(row, 'span.jobShifttype.hidden-phone')
        or text(row, 'span.jobShifttype')
        or ''
    )
    # Closing date — look for any td/span containing a date-like string
    closing = ''
    for td in row.find_all('td'):
        t = td.get_text(' ', strip=True)
        if re.search(r'\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4}|\d{1,2}\s+\w+\s+\d{4}', t):
            closing = t
            break

    if not title and not apply_url:
        continue  # blank / spacer row

    job_id = ''
    if apply_url:
        m = re.search(r'/(\d+)/?(?:\?.*)?$', apply_url)
        if m:
            job_id = m.group(1)

    desc_parts = []
    if department:
        desc_parts.append(f'Department: {department}')
    if shift:
        desc_parts.append(f'Type: {shift}')
    desc_html = '<ul>' + ''.join(f'<li>{p}</li>' for p in desc_parts) + '</ul>' if desc_parts else ''

    print(f'  Job: {title!r}  location={location!r}  closing={closing!r}  url={apply_url!r}', flush=True)

    jobs.append({
        'externalid':   job_id,
        'jobtitle':     title,
        'locationcity': location,
        'jobtenure':    shift or 'Permanent',
        'type':         closing,
        'date':         now_str,
        'applyURL':     apply_url,
        'description':  desc_html,
    })

print(f'\nTotal jobs extracted: {len(jobs)}', flush=True)

# ── Generate XML ──────────────────────────────────────────────────────────────
from xml.dom import minidom

root = ET.Element('jobs')
for j in jobs:
    job_el = ET.SubElement(root, 'job')
    for tag, val in j.items():
        child = ET.SubElement(job_el, tag)
        child.text = val or ''

raw_xml = ET.tostring(root, encoding='unicode')
dom    = minidom.parseString(raw_xml)
pretty = dom.toprettyxml(indent='  ', encoding=None)
pretty = re.sub(r'^<\?xml[^?]*\?>\n?', '', pretty)
output = '<?xml version="1.0" encoding="UTF-8" ?>\n' + pretty

with open(OUTPUT_XML, 'w', encoding='utf-8') as fh:
    fh.write(output)

print(f'Written {len(jobs)} job(s) to {OUTPUT_XML}', flush=True)
