'use strict';

const { BlobServiceClient } = require('@azure/storage-blob');
const { parse: parseHTML }  = require('node-html-parser');

const CAREERS_URL      = 'https://careers.gloucestershire.gov.uk/go/All-City-Council-Jobs/8557855/';
const BASE_URL         = 'https://careers.gloucestershire.gov.uk';
const CONTAINER        = 'jobs-cache';
const BLOB_NAME        = 'jobs-feed.xml';
const CACHE_MAX_AGE_MS = 4 * 60 * 60 * 1000; // 4 hours

/* ─── Entry point ──────────────────────────────────────────────────────── */

module.exports = async function (context, req) {
  const connStr = process.env.AZURE_STORAGE_CONNECTION_STRING;

  // 1. Try to serve from blob cache
  if (connStr) {
    const cached = await tryGetCache(connStr, context);
    if (cached) {
      context.res = xmlResponse(cached);
      return;
    }
  }

  // 2. Fetch & scrape live data
  let xml;
  try {
    const html = await fetchPage(CAREERS_URL);
    xml = scrapeToXml(html);
  } catch (err) {
    context.log.error('Failed to fetch/scrape jobs:', err.message);
    context.res = { status: 502, body: 'Failed to fetch jobs from source.' };
    return;
  }

  // 3. Write to blob cache (best-effort)
  if (connStr) {
    await tryPutCache(connStr, xml, context);
  }

  context.res = xmlResponse(xml);
};

/* ─── Blob cache helpers ───────────────────────────────────────────────── */

async function tryGetCache(connStr, context) {
  try {
    const blobClient = BlobServiceClient
      .fromConnectionString(connStr)
      .getContainerClient(CONTAINER)
      .getBlobClient(BLOB_NAME);

    const props = await blobClient.getProperties();
    const ageMs = Date.now() - new Date(props.lastModified).getTime();

    if (ageMs < CACHE_MAX_AGE_MS) {
      const download = await blobClient.download();
      return await streamToString(download.readableStreamBody);
    }

    context.log.info(`Cache stale (${Math.round(ageMs / 60000)} min old) — refreshing.`);
  } catch (err) {
    if (err.statusCode !== 404) {
      context.log.warn('Cache read failed:', err.message);
    }
  }
  return null;
}

async function tryPutCache(connStr, xml, context) {
  try {
    const containerClient = BlobServiceClient
      .fromConnectionString(connStr)
      .getContainerClient(CONTAINER);

    await containerClient.createIfNotExists({ access: 'blob' });

    const blockClient = containerClient.getBlockBlobClient(BLOB_NAME);
    await blockClient.upload(xml, Buffer.byteLength(xml, 'utf8'), {
      blobHTTPHeaders: { blobContentType: 'application/xml; charset=utf-8' }
    });

    context.log.info('Cache written to blob storage.');
  } catch (err) {
    context.log.warn('Cache write failed (non-fatal):', err.message);
  }
}

/* ─── HTTP fetch ───────────────────────────────────────────────────────── */

async function fetchPage(url) {
  const res = await fetch(url, {
    headers: {
      'Accept':     'text/html,application/xhtml+xml,*/*',
      'User-Agent': 'Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)'
    },
    signal: AbortSignal.timeout(15000)
  });
  if (!res.ok) throw new Error(`HTTP ${res.status} from ${url}`);
  return res.text();
}

/* ─── Scraper ──────────────────────────────────────────────────────────── */

function scrapeToXml(html) {
  const root  = parseHTML(html);
  const table = root.querySelector('table#searchresults');

  const SKIP_IDS = new Set(['search-results-header', 'search-results-filter']);
  const rows = table
    ? [...table.querySelectorAll('tr')].filter(tr => !SKIP_IDS.has(tr.id))
    : [];

  const nowStr = new Date().toUTCString().replace(/\d{2}:\d{2}:\d{2}/, '00:00:00');
  const jobs   = [];

  for (const row of rows) {
    const getText = sel => {
      const el = row.querySelector(sel);
      return el ? el.textContent.trim() : '';
    };
    const getHref = sel => {
      const el = row.querySelector(sel);
      if (!el) return '';
      const h = el.getAttribute('href') || '';
      return h.startsWith('/') ? BASE_URL + h : h;
    };

    const title = getText('span.jobTitle.hidden-phone a')
      || getText('a.jobTitle-link')
      || getText('span.jobTitle a')
      || getText('span.jobTitle');

    const applyURL = getHref('span.jobTitle.hidden-phone a')
      || getHref('a.jobTitle-link')
      || getHref('span.jobTitle a')
      || getHref('a');

    if (!title && !applyURL) continue;

    const location = getText('span.jobLocation.hidden-phone')
      || getText('span.jobLocation')
      || 'Gloucester';

    const tenure = getText('span.jobFacility.hidden-phone')
      || getText('span.jobFacility')
      || getText('span.jobDepartment')
      || 'Permanent';

    const shiftRaw = getText('span.jobShifttype.hidden-phone')
      || getText('span.jobShifttype')
      || '';
    const dateMatch = shiftRaw.match(/\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4}/);
    const closing   = dateMatch ? dateMatch[0] : '';

    const idMatch = applyURL.match(/\/(\d+)\/?(?:\?.*)?$/);
    const id      = idMatch ? idMatch[1] : '';

    jobs.push({ id, title, location, tenure, closing, nowStr, applyURL });
  }

  return buildXml(jobs);
}

function buildXml(jobs) {
  const esc = s => (s || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');

  const jobsXml = jobs.map(j => `  <job>
    <externalid>${esc(j.id)}</externalid>
    <jobtitle>${esc(j.title)}</jobtitle>
    <locationcity>${esc(j.location)}</locationcity>
    <jobtenure>${esc(j.tenure)}</jobtenure>
    <type>${esc(j.closing)}</type>
    <date>${esc(j.nowStr)}</date>
    <applyURL>${esc(j.applyURL)}</applyURL>
    <description></description>
  </job>`).join('\n');

  return `<?xml version="1.0" encoding="UTF-8" ?>\n<jobs>\n${jobsXml}\n</jobs>\n`;
}

/* ─── Utilities ────────────────────────────────────────────────────────── */

function xmlResponse(body) {
  return {
    headers: {
      'Content-Type':  'application/xml; charset=utf-8',
      'Cache-Control': 'public, max-age=3600'
    },
    body
  };
}

function streamToString(stream) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    stream.on('data',  chunk => chunks.push(Buffer.from(chunk)));
    stream.on('end',   ()    => resolve(Buffer.concat(chunks).toString('utf8')));
    stream.on('error', reject);
  });
}
