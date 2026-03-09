# Development Log: Gloucester City Council Careers Website

**Project:** Public-facing jobs board for Gloucester City Council
**Platform:** Azure Static Web Apps, GitHub Actions automation
**Period:** 6 March 2026 – 9 March 2026
**Status:** Working MVP with automated feed refresh

---

## What We Were Trying to Build

The goal was simple to describe: give members of the public a clean, accessible web page where they can browse current job vacancies at Gloucester City Council. Candidates should be able to filter and search jobs, see closing dates at a glance, and click through to apply on the council's existing recruitment system.

The jobs themselves come from Gloucester's careers portal (powered by SAP SuccessFactors / RMK), so we did not want to host or manage the job data ourselves — we just wanted to pull it in automatically and display it nicely.

The end result is a static HTML page hosted on Azure Static Web Apps, with a GitHub Actions workflow that scrapes the council's recruitment portal every four hours, saves the job data as an XML file in the repository, and deploys the update automatically.

---

## Step 1: The Initial Commit — Getting Something on Screen

**Lesson: Start with the simplest thing that could possibly work.**

The very first commit (`bbf839b`) added a single file: `jobs/index.html`. This page was designed to:

- Read a local XML file (`jobs-feed.xml`) using JavaScript's built-in `DOMParser`
- Parse each `<job>` element and render it as a card on screen
- Show job title, location, contract type, closing date, and an Apply link
- Work entirely in the browser — no server, no build step, no framework

The XML format was based on Vacancy Filler / HireRoad, a common format in UK public sector recruitment systems. This was a deliberate choice: by targeting a standard format, the page could potentially work with many councils' data feeds, not just Gloucester's.

**Why this matters:** Starting with a static HTML file means anyone can open it in a browser directly from their file system. There is nothing to install, configure, or build. This approach pays dividends throughout the project — every fix and test is instant.

---

## Step 2: Deploying to Azure Static Web Apps

**Lesson: Get it live early, even if it's not finished. Real hosting reveals problems that localhost hides.**

Commits `8de0005` through `d22d523` cover the deployment to Azure. This involved several iterations:

### First attempt: Azure auto-generated a workflow file
When you connect a GitHub repository to Azure Static Web Apps through the Azure Portal, it automatically creates a GitHub Actions workflow file. This is convenient but also causes problems if the file is wrong — Azure tries to build your project using a tool called Oryx, which detects the project type and runs an appropriate build command.

### Problem: Oryx thought this was a Node.js project
Because there was no `package.json`, Oryx was confused about how to build the site. The fix came in two parts:

1. **Add `skip_app_build: true`** in the workflow YAML to tell Azure "don't try to build this, just deploy the files as-is."
2. **Add a minimal `package.json`** with a dummy `build` script. This was a belt-and-braces approach to keep Oryx satisfied.

```json
{
  "scripts": { "build": "echo 'Static site — no build step required'" }
}
```

### Problem: The root URL showed a blank page
The site was configured to serve from `/`, but the actual jobs page lived at `/jobs/`. The fix was `staticwebapp.config.json` — Azure's routing configuration file:

```json
{
  "routes": [
    { "route": "/", "redirect": "/jobs/", "statusCode": 302 }
  ],
  "navigationFallback": {
    "rewrite": "/jobs/index.html",
    "exclude": ["/jobs/*", "/assets/*"]
  }
}
```

**Why this matters:** The routing config is the control panel for a static web app. It handles redirects, rewrites, and 404 fallbacks without any server code. Getting this right early means the URL structure is clean from the start.

---

## Step 3: Adding Automated Feed Refresh

**Lesson: Automation is what turns a prototype into a product. A jobs page with stale data is worse than no jobs page.**

Commit `ae2b511` introduced two key pieces:

1. **A filter** to only show Gloucester City Council jobs (the source URL returns jobs from across Gloucestershire County Council's entire estate)
2. **A GitHub Actions workflow** (`refresh-jobs.yml`) that runs on a schedule to keep the XML feed up to date

The workflow was scheduled to run every four hours using a cron expression:

```yaml
on:
  schedule:
    - cron: '0 */4 * * *'
```

It worked like this:
1. Fetch the jobs XML from the council's external careers portal
2. Filter to keep only Gloucester City Council jobs
3. Write the result to `jobs/jobs-feed.xml`
4. Commit and push the updated file back to the repository
5. Azure picks up the new commit and redeploys automatically

**Why this matters:** This is the architectural heart of the whole system. By storing the feed as a file in the repository, the website always has data even if the source is temporarily unavailable. The static site never makes a live network request to an external service — it just reads the local XML file.

---

## Step 4: Debugging the Feed — Nothing Was Appearing

**Lesson: Debug with real data before assuming your code is right.**

This was the most iterative phase of the project. Commits `d82ed8b` through `de425b9` represent a series of investigations and fixes.

### Problem: The XML feed was empty
The workflow was running but the feed had no jobs. To find out why, the workflow was temporarily updated to dump the full HTTP response headers and body to the console. This revealed that the external URL was responding — but with an HTML page, not XML.

**The source portal doesn't have an XML feed.** The Gloucester careers portal uses SAP SuccessFactors (branded as RMK), which serves an HTML search results page, not a machine-readable feed.

### The fix: Switch from XML fetching to HTML scraping
Commit `de425b9` replaced the XML fetch with a Python script (`scripts/scrape_jobs.py`) using BeautifulSoup to parse the HTML page. The script:

1. Fetches the HTML from `https://careers.gloucestershire.gov.uk/go/All-City-Council-Jobs/8557855/`
2. Finds the results table (`table#searchresults`)
3. Reads each row and extracts data from specific CSS class names:
   - `span.jobTitle` → job title
   - `span.jobLocation` → location
   - `span.jobFacility` → contract type (e.g., Permanent, Fixed Term)
   - `span.jobShifttype` → contains the closing date
4. Generates XML in the format the front-end already understands

**Why this matters:** Web scraping is often the only option when a third-party system doesn't provide an API or feed. The key is to find stable CSS class names (not positional selectors like "third column") so that minor layout changes don't break the scraper.

---

## Step 5: Fixing the Field Mapping

**Lesson: Never assume field names mean what they sound like. Check the actual data.**

Commit `eb5b3fd` fixed a subtle but important bug. The SAP SuccessFactors HTML uses field names that don't match their actual content:

| CSS Class | Sounds like | Actually contains |
|-----------|-------------|-------------------|
| `span.jobFacility` | Facility/location? | Contract type (Permanent / Fixed Term) |
| `span.jobShifttype` | Shift type? | Closing date |

The initial scraper had these mapped incorrectly, meaning contract types were showing as closing dates and vice versa. Once the actual page HTML was inspected carefully, the correct mapping was obvious — but it required looking at real data rather than guessing from the field name.

---

## Step 6: Removing the URL Filter That Broke Everything

**Lesson: A filter that's too strict produces the same result as no data at all.**

Commit `eaef17a` removed a URL filter that had been silently discarding every single job. The original intent was to filter jobs to only show those from "Gloucester City Council" by checking if the job URL contained `/GloucesterCity/`. But the actual job URLs from the portal use a different path structure entirely — so the filter matched nothing, and the feed was always empty.

The fix was to remove the URL-based filter and instead rely on fetching from the correct URL (the "All City Council Jobs" listing), which already scopes results to the right employer.

**Why this matters:** Defensive filtering is good, but filtering based on assumptions about data structure is dangerous. Always validate your assumptions against real data before shipping a filter.

---

## Step 7: Fixing the Workflow's Git Push

**Lesson: GitHub Actions has strict permission rules. Understand them before you start.**

Commits `c705f00` through `4e24323` fixed a series of problems with the workflow's ability to commit and push the updated XML file.

### Problem 1: Insufficient permissions
The workflow was failing with a 403 error when trying to push. GitHub organisations can restrict the default `GITHUB_TOKEN` from writing to repositories. The fix was to use a Personal Access Token (PAT) stored as a repository secret:

```yaml
env:
  GITHUB_TOKEN: ${{ secrets.PERSONAL_ACCESS_TOKEN }}
```

### Problem 2: Push rejected because local branch was behind remote
When two workflow runs happen close together, the second push gets rejected because the remote branch has moved on. The fix was to `git pull --rebase` before pushing:

```bash
git pull --rebase origin ${{ github.ref_name }}
git push origin ${{ github.ref_name }}
```

### Problem 3: `HEAD` ambiguity in the workflow
Using `HEAD` to refer to the current branch inside a GitHub Actions checkout doesn't always work cleanly. The fix was to use `github.ref_name`, which is a reliable variable that always contains the current branch name.

**Why this matters:** GitHub Actions workflows that write back to the repository are a common pattern but have several sharp edges. The permission model, conflict handling, and branch reference all need to be handled explicitly.

---

## Step 8: The Front-End — Making It Look Good and Work Well

**Lesson: Accessibility and design are not optional extras — build them in from the start.**

The `jobs/index.html` file grew from a basic proof of concept into a fully-featured, accessible jobs board. Key features added over several commits:

### Search and Filtering
- Keyword search across job title, location, and salary
- Dropdown filters for location and contract type
- "Clear filters" button
- 250ms debounce on the keyword input so it doesn't search on every keystroke

### Sorting
- By closing date (soonest first)
- By job title (A–Z)
- By date posted (newest first)

### Urgency Indicators
Jobs closing within 3 days get a red "Closing soon" badge. Jobs closing within 7 days get an amber warning. This is calculated fresh every time the page loads, so it's always accurate.

### Accessibility (WCAG AA)
- Skip link at the top to jump straight to the job listings
- Screen reader announcements when filter results change (using ARIA live regions)
- Visible keyboard focus styles on every interactive element
- Semantic HTML throughout — job metadata uses `<dl>/<dt>/<dd>` (description list) rather than plain divs
- SVG icons are hidden from screen readers with `aria-hidden="true"`

### Security
- All job data displayed on screen is HTML-entity-escaped before being inserted into the DOM. This prevents any malicious content in the job feed from executing as JavaScript (XSS protection).

### Design
- Gloucester City Council green (`#00703C`) as the primary colour
- Inspired by GOV.UK design patterns — familiar to anyone who uses UK government websites
- Responsive grid layout that works on mobile, tablet, and desktop
- Respects the user's "reduce motion" preference for animations

---

## Where We Are Now: A Working System

The current state of the project (as of 9 March 2026):

1. **A live jobs page** at the Azure Static Web Apps URL, showing current Gloucester City Council vacancies
2. **Automated refresh** every four hours via GitHub Actions
3. **Clean, accessible front-end** with search, filtering, and sorting
4. **Governance documentation** — security policy, data classification, and usage guidelines in place
5. **Two bonus templates** in the repository (`council-homepage/` and `council-modern/`) showing what a full council website could look like using the same static, no-dependency approach

---

## Summary of Key Technical Lessons

| Lesson | Where it Came From |
|--------|-------------------|
| Start static — no framework, no build step | Initial deployment struggles with Azure Oryx |
| Debug with real data from day one | Empty feed mystery |
| Scrape HTML when there's no API | SAP SuccessFactors has no XML feed |
| Never trust field names — check the actual data | jobFacility / jobShifttype confusion |
| Strict filters that match nothing are invisible bugs | URL filter dropping all jobs |
| GitHub Actions write-back needs explicit permission handling | PAT token, rebase, ref_name |
| Escape all output to prevent XSS | Security review of front-end code |
| Accessibility is a feature, not an afterthought | WCAG compliance built in from the start |

---

## To-Do List: Taking This to a Safe, Secure, Production Site

The current site works as a proof of concept, but several things need to be done before it should be considered production-ready for public access. Here is a prioritised list:

---

### Security

- [ ] **Move the Personal Access Token to a proper secret management system.** Currently the PAT is stored as a GitHub Actions secret, which is fine for now, but it should be scoped to the minimum permissions needed (contents: write on this repo only) and rotated regularly. Document who is responsible for rotation.

- [ ] **Add a Content Security Policy (CSP) header.** Azure Static Web Apps supports custom headers in `staticwebapp.config.json`. A CSP prevents injected scripts from running even if an XSS attack somehow slips through. At minimum, set `default-src 'self'` and explicitly list any allowed external domains.

- [ ] **Add security headers across the board.** Using `staticwebapp.config.json`, add:
  - `X-Content-Type-Options: nosniff`
  - `X-Frame-Options: DENY` (prevents clickjacking)
  - `Referrer-Policy: strict-origin-when-cross-origin`
  - `Permissions-Policy` to disable camera, microphone, geolocation

- [ ] **Review the scraper's User-Agent string.** The workflow currently sends a Googlebot user-agent to avoid being blocked. This is a grey area ethically and technically — check whether the careers portal's terms of service permit automated access, and if so, use a more honest user-agent like `GloucesterCityCouncilBot/1.0`.

- [ ] **Add rate limiting awareness to the scraper.** Currently the scraper makes one request and exits. If the workflow is triggered manually multiple times in quick succession, it could look like an attack. Add a check: if the last successful fetch was less than 30 minutes ago, skip the request.

---

### Reliability and Monitoring

- [ ] **Set up alerting when the feed goes stale.** If the scraper fails repeatedly and no one notices, the jobs page will show outdated listings. Add a GitHub Actions step that posts to a Slack channel or sends an email if the feed has not been updated in more than 12 hours.

- [ ] **Add a "last updated" timestamp to the page.** The `jobs-feed.xml` file should include a `<lastUpdated>` element, and the page should display it. This tells visitors (and council staff) how fresh the data is.

- [ ] **Handle scraper failures gracefully.** Currently if the scraper produces invalid XML, the workflow fails and the old file is preserved (due to the XML validation step). But the error is silent. Add explicit error notifications.

- [ ] **Consider a fallback for when the source site is down.** The page already handles an empty feed gracefully (showing a "no jobs found" message), but consider adding copy like "We are currently unable to retrieve live job listings. Please visit [link] directly."

---

### Performance

- [ ] **Add HTTP caching headers.** Tell browsers how long to cache the jobs page and the XML feed. The XML feed changes at most every four hours, so `Cache-Control: public, max-age=14400` is appropriate for it. The HTML page can be cached more aggressively.

- [ ] **Consider reducing the feed refresh frequency during off-hours.** Running every four hours at 3am serves no purpose if no one is posting jobs at 3am. Change the cron to run more frequently during business hours (e.g., every 2 hours 8am–6pm Monday–Friday) and less frequently at night.

- [ ] **Enable compression.** Azure Static Web Apps does this automatically, but verify it is enabled by checking the response headers in browser DevTools. Compressed XML and HTML are significantly smaller over the network.

---

### Accessibility and User Experience

- [ ] **User-test the page with a real screen reader.** The code is written to WCAG AA standards, but automated checks don't catch everything. Test with NVDA (free, Windows) or VoiceOver (built into macOS and iOS) to verify the experience is genuinely usable.

- [ ] **Add pagination or lazy loading.** If the number of jobs grows significantly (more than 30–40 at once), the single-page layout will become hard to navigate. Plan for this now rather than retrofitting later.

- [ ] **Add a "no results" suggestion.** When a search returns no jobs, suggest the user try clearing their filters or widening their search, and provide the direct link to the full Gloucestershire careers portal.

- [ ] **Test on older mobile devices.** The CSS grid and JavaScript features used are well-supported, but confirm the experience on a real mid-range Android phone at 4G speeds.

---

### Content and Governance

- [ ] **Get sign-off from the council's communications team** on the wording, branding, and overall presentation before the URL is publicised.

- [ ] **Add a privacy notice.** Even though the page collects no personal data, best practice for a council website is to include a link to the privacy notice and explain that no cookies are set (other than any Azure infrastructure cookies).

- [ ] **Add a cookies notice (or confirmation that none are needed).** Check whether Azure Static Web Apps sets any first-party or third-party cookies. If it does, a cookie consent banner is required under UK PECR regulations.

- [ ] **Register the URL with the council's web team** so it appears in the council's sitemap and can be linked from the main website and intranet.

- [ ] **Document the operational process.** Who is responsible for the site? What happens if a job is listed incorrectly? Who should staff contact if they notice a problem? Write a brief operations runbook (one page is enough).

---

### Infrastructure

- [ ] **Set up a custom domain.** The current Azure-generated URL (ending in `.azurestaticapps.net`) is not suitable for a public-facing council service. Work with the council's IT team to configure `jobs.gloucester.gov.uk` or a similar subdomain, and add an SSL certificate (Azure handles this automatically for custom domains).

- [ ] **Set up Azure Application Insights** (or equivalent) for basic usage monitoring — page views, browser types, geographic distribution. This is useful for reporting to councillors and management, and helps identify if something goes wrong. Make sure this complies with the council's data protection policies.

- [ ] **Review the Azure Static Web Apps pricing tier.** The free tier is appropriate for a pilot but has limits on bandwidth and features. Confirm the council's Azure subscription has the right tier for production use.

- [ ] **Add branch protection to `main`.** Currently it may be possible for anyone with repository write access to push directly to main. Require pull request reviews before merging, and require the Azure deployment to succeed before a merge is allowed.

- [ ] **Set up a staging environment.** Azure Static Web Apps automatically creates preview deployments for pull requests — make sure this feature is enabled. This means any changes can be reviewed on a live URL before going to production.

---

### Future Enhancements (Nice to Have)

- [ ] **Email alerts for new jobs.** Allow visitors to sign up for email notifications when new jobs matching their interests are posted. This would require a small backend (e.g., an Azure Function) and email service integration.

- [ ] **Job category filtering.** Group jobs by department or service area to help candidates find relevant roles more quickly.

- [ ] **Structured data markup.** Add `JobPosting` schema.org markup to the job cards so they appear in Google for Jobs search results, significantly increasing visibility.

- [ ] **Share functionality.** Add a "copy link" or share button for individual job listings so candidates can easily share with contacts.

- [ ] **Printable job details view.** Some candidates want to print a job description before an interview. A simple print stylesheet would handle this.

---

*This document was generated on 9 March 2026 as part of the development handover process.*
