# Plan: a public site for the maps and reports

Status: draft, 2026-11-24. Nothing built yet.

## Goal

One public place where city staff, Safe Routes to School teams and advocates
can see, for each city we have tested:

- where people on bikes are being hurt (the crash map),
- where the risk model expects trouble (the predicted-risk map and top
  corners),
- how children get to school, and to places like downtown Los Altos, and
  where those routes meet traffic (from walkbike-routes),
- how the county compares on emergency department visits and hospital
  admissions for bicycle injuries (the EpiCenter reports).

## When

Launch once these are settled:

1. The risk model is final enough to show without a "draft" label.
2. The hospital figures (ED visits and admissions) are final.
3. walkbike-routes is either out of draft or its section on the site carries
   a clear "draft" label (see the open questions at the end).

The site plumbing can be built before then and deployed privately (see
"Private preview").

## Hosting

Cloudflare Pages, uploaded directly from a laptop with
`npx wrangler pages deploy site/ --project-name <name>`. Chosen over Firebase
(which hosts geoffdavis.net) because:

- no bandwidth limit or bill if a map is shared widely (Firebase's free plan
  stops serving after about 360 MB a day);
- Cloudflare Access can password-protect the site, or a part of it, for up to
  50 people free, for showing drafts to a city before they are public;
- built-in analytics without cookies.

Limits to keep in mind: 25 MB per file and 20,000 files per site. Today's
largest map is 8.4 MB (San Francisco). A citywide Los Angeles map could come
near the limit; showing Los Angeles by Community Plan Area keeps each file
small.

The site cannot be built in CI, because the crash records in `data/` are not
committed. Every build and deploy runs locally.

Domain: a subdomain of geoffdavis.net (DNS at Porkbun), pointed at the
Pages project with a CNAME. The DNS can stay at Porkbun.

## Where the code lives

A new small repository, `bike-safety-site` (name to be decided), next to the
two projects. It holds:

- `cities.yaml`: the cities to publish, each with its county, the
  bike-safety-ca output folder, the walkbike-routes output folders, and
  headline numbers or a pointer to where they are read from;
- page templates (Jinja) and one stylesheet;
- `build.py`: reads `cities.yaml`, copies the current outputs from
  `../bike-safety-ca/output/...` and `../walkbike-routes/output/...` into
  `site/`, renders the pages, and checks the result (below);
- `make site`, `make preview` (deploy to a preview URL) and `make publish`.

`site/` is not committed. The repository holds templates and settings only,
so the rules on record data are simple to keep: no crash, party or victim
records, no EpiCenter tables beyond what the published reports already show.

Neither project needs to know about the site. Each only needs to write its
outputs to paths the build can find. One change is needed for that, below.

## Stable paths

Output folders today are dated (`output/los_altos_2026-11-22/`). The site
uses fixed paths instead, so links sent to city staff keep working:

```text
/                              home
/methods/                      how the maps and model work
/credits/                      sources and licences
/<city>/                       city page
/<city>/crash-map.html
/<city>/predicted-risk.html    if the risk view is a separate file
/<city>/routes.html            all schools and other destinations on one map
/<city>/<name>.pdf             print versions
/county/<county>/              hospital report as HTML, with its PDF
```

`cities.yaml` names which dated folder feeds each city, so updating a city
is a one-line change and a rebuild. Each page states the data period and the
date it was built ("crashes 2015–2024, updated November 2026").

## Pages

### Home

- One paragraph: what this is, who it is for, and that it comes from public
  records.
- The cities, as a simple list grouped by county to start (a clickable
  California map can come later). Each city has one or two headline lines,
  for example the number of cyclist injury crashes in the last five years and
  the top-ranked corner.
- Links to Methods and Credits.

### City page

- The crash map and the predicted-risk view, opened in a new page (they are
  large). A small static image of each as the link, so the city page itself
  stays light.
- The top corners list, with a sentence on what "top" means.
- Routes to school and to other destinations, from walkbike-routes: one map
  for the city with every destination on it, and its "fix first" list.
- PDF downloads.
- "Hospital visits in <county>" with a one-line figure and a link to the
  county page.
- Credits for everything on the page.

### County page

The hospital report (today `hospital_<county>.md` and `.pdf`) turned into
HTML, with its charts. Only counties with at least one published city at
first; the statewide e-bike report can have its own page.

### Methods

Written for city staff, not statisticians: what the crash map shows and
leaves out (police reports miss most falls), what the risk model predicts,
how far to trust it, and what walkbike-routes models. Drawn from
`docs/guide.md` and the walkbike-routes README, and linked to them.

## Credits and obligations

- TIMS and CCRS credit lines on every page with crash-derived figures (the
  maps already carry them).
- CDPH/EpiCenter credit on every hospital figure, and **tell CDPH of the
  publication** (<EpiCenter@cdph.ca.gov>) when the hospital pages go live, as
  the EpiCenter user agreement asks.
- OpenStreetMap and Census Bureau credits where their data is used.
- A short "about" line: who made this, how to report a mistake.

## Checks in `build.py`

Before a deploy, the build fails if:

- any file is over 25 MB;
- a page links to a file that is not in `site/`;
- a page with crash-derived figures lacks the TIMS and CCRS credits, or a
  hospital page lacks the CDPH credit;
- a file under `site/` is not one the build put there (no stray tables or
  logs from `output/`). The build copies by an allow-list of file types and
  names, never whole folders.

## Private preview

Until launch, deploy to the Pages project behind Cloudflare Access (an email
list), or use only preview URLs, which are not linked anywhere. Useful for
showing a city its page before it is public.

## Changes needed in the two projects

- **bike-safety-ca:** nothing required at first; the build reads today's
  dated folders. Later, possibly a small JSON summary per city (headline
  numbers, data period) so the build does not parse markdown.
- **walkbike-routes:** a Los Altos run with schools and downtown in one map
  (`los_altos_schools.yaml` and `los_altos_downtown.yaml` exist as separate
  configs). Its `manifest.json` may already give the build what it needs.

## Later

- Crashes and predicted risk along the school routes, in one view: which
  streets carry many children's trips and score high risk. A modelling task,
  not part of the first site.
- A clickable state map on the home page.
- Per-school route maps if people ask for them (about 5 MB each).

## Open questions for Geoff

1. Site name and subdomain.
2. Which cities go in the first release. Candidates: the cities with
   configs where the model has been checked (Los Altos, Palo Alto, San
   Francisco, ...).
3. Show walkbike-routes as "draft" at launch, or wait for it?
4. Which other destinations besides schools, per city (downtown Los Altos is
   one)?
5. Should hospital pages cover every California county, or only the counties
   of published cities?
6. A separate repository for the site, as proposed, or a `site/` folder in
   bike-safety-ca?
