# Reflex Research Workbench Design

## Goal

Replace the current NiceGUI frontend with a Reflex frontend while keeping the existing FastAPI backend, SQLite database, download engine, and PDF file routing. The new frontend should feel like a real research workbench for private literature collection, not a generic admin dashboard or marketing-style app.

## Product Intent

The app is used to:

- search targeted journals by keyword
- review metadata and OA availability
- batch-select papers for download
- inspect download failures and retry them
- browse a local literature library with PDF-first workflows
- maintain the journal scope for future searches

The UI should optimize for repeated use, dense information, and calm control. It should feel closer to a research database or desktop workbench than a landing page.

## Design Direction

Adopt a two-column research workbench layout.

- Left side: persistent app navigation and utility context
- Main area: page-specific working surface
- Content style: dense, structured, and scan-friendly
- Visual tone: archival, editorial, and operational

The interface should avoid:

- oversized hero sections
- decorative feature cards
- split marketing layouts
- generic SaaS dashboard styling
- oversized empty whitespace

## Information Architecture

The Reflex app should expose four primary pages:

1. Search
2. Library
3. Downloads
4. Journals

Each page should feel like a working view, not a document page.

### Search

Purpose: run CrossRef journal searches, inspect OA status, and start batch downloads.

Primary regions:

- search command bar
- compact filter strip
- journal selection panel
- result summary strip
- dense result list
- sticky batch action bar

Behavior:

- the search bar is the visual anchor of the page
- filters remain compact and immediately actionable
- result rows are list-like, not card-heavy
- OA/download/manual states are visible at a glance
- batch selection should feel fast and obvious

### Library

Purpose: search the local stored corpus and open PDFs quickly.

Primary regions:

- local search bar
- scope toggle: all / pdf / metadata
- journal filters
- dense result list
- pagination controls

Behavior:

- prioritize title, journal, DOI, and PDF availability
- opening a PDF should be a first-class action
- metadata-only records should still remain useful and visible

### Downloads

Purpose: track task progress, inspect failures, and retry.

Primary regions:

- task list with status summary
- selected task detail panel
- progress summary
- failed-item inspection table
- retry controls

Behavior:

- desktop layout should use a split workbench view when possible
- a selected task should reveal detailed per-item state without route friction
- failure details should be visible without expanding giant panels everywhere

### Journals

Purpose: maintain the journal scope for search.

Primary regions:

- add-journal form
- existing journal table
- enabled/disabled state
- counts for indexed records and downloaded PDFs

Behavior:

- stay utilitarian and compact
- keep validation feedback inline and immediate

## Layout System

### App Shell

The Reflex app should use a persistent shell:

- left navigation rail on desktop
- top bar only for current page title and utility actions
- main content container with strong vertical rhythm
- mobile layout collapses the left rail into a drawer or top sheet

The shell should make it easy to move repeatedly between Search, Library, and Downloads.

### Density Rules

- prefer rows and structured panels over large cards
- keep corner radii restrained
- use compact spacing for filters and list controls
- reserve larger spacing for page transitions and section boundaries only
- surface the most useful metadata in the first visible line of each result

## Visual Language

The visual direction should be "research workbench", not generic SaaS.

### Palette

- background: warm paper / cool off-white
- text: deep ink blue
- accent: sober green or mineral teal for positive states
- warning: muted amber
- failure: restrained brick red

Avoid purple-heavy palettes and flat white-on-light-gray monotony.

### Typography

- headings: expressive but serious
- body: readable UI sans
- metadata: compact and crisp
- DOI and status text: tabular where useful

Typography should add character without reducing legibility.

### Motion

Use only a few purposeful transitions:

- page-level fade/slide when changing routes
- staggered reveal for result rows
- subtle emphasis for new task states

Do not add ornamental animation.

## Frontend Architecture

Create a dedicated Reflex frontend app instead of embedding Reflex into the existing NiceGUI structure.

Proposed structure:

- `frontend/` or `reflex_app/` for Reflex code
- shared theme module
- shared layout module
- page modules for Search, Library, Downloads, Journals
- state modules aligned with each page's workflow
- API client module for FastAPI calls

Reflex responsibilities:

- page routing
- component layout
- client-side state
- search/filter forms
- polling task status
- action feedback

FastAPI responsibilities remain:

- database access
- background search/download execution
- PDF serving
- journal validation against CrossRef

## API Boundary Needed For Reflex

The current NiceGUI pages call repository and downloader logic directly. Reflex cannot reuse that shape as-is, so the backend needs JSON endpoints for the new frontend.

Minimum required API surface:

- `GET /api/journals`
- `POST /api/journals`
- `PATCH /api/journals/{issn}`
- `DELETE /api/journals/{issn}`
- `POST /api/search-tasks`
- `GET /api/search-tasks`
- `GET /api/search-tasks/latest`
- `GET /api/search-tasks/{id}`
- `GET /api/search-tasks/{id}/papers`
- `POST /api/download-tasks`
- `GET /api/download-tasks`
- `GET /api/download-tasks/{id}`
- `POST /api/download-tasks/{id}/retry`
- `POST /api/download-tasks/{id}/items/{doi}/retry`
- `GET /api/library/search`

The API should reuse existing repo/downloader logic rather than duplicate it.

## State Model

Reflex state should be split by workflow instead of one monolithic global store.

Recommended state modules:

- `ShellState`: current route affordances, nav, responsive drawer state
- `SearchState`: query form, active search task, selected result DOIs
- `LibraryState`: query, scope, journal filters, page index
- `DownloadsState`: task list, selected task, polling status
- `JournalsState`: add form, table data, mutation feedback

State rules:

- search results belong to a persisted task id, not transient local-only state
- downloads should poll while active and stop polling when not needed
- page state should survive route changes when practical
- user actions should return clear optimistic or loading feedback

## Migration Strategy

Implement in phases rather than replacing everything at once.

### Phase 1

- add Reflex app scaffold
- define theme, shell, routing
- keep existing FastAPI app alive

### Phase 2

- add JSON API endpoints on FastAPI
- verify endpoints with tests

### Phase 3

- implement Search page in Reflex
- implement Library page in Reflex

### Phase 4

- implement Downloads page in Reflex
- implement Journals page in Reflex

### Phase 5

- wire PDF open flow
- run visual and interaction verification
- remove or retire NiceGUI page registration

## Testing Strategy

Testing should cover both backend API correctness and frontend route rendering.

Backend:

- API endpoint tests for search, library, downloads, journals
- preserve current downloader and config tests

Frontend:

- smoke tests for main Reflex routes
- state transition checks where feasible
- browser verification for desktop and mobile layouts

Manual verification should include:

- run a search
- inspect result states
- launch a download task
- retry a failed item
- browse local library
- add and disable a journal

## Risks And Constraints

- Reflex migration requires extracting UI-coupled logic from NiceGUI pages into reusable backend endpoints
- polling and task updates need careful handling to avoid wasteful refresh patterns
- replacing the frontend framework means temporary duplication during migration
- the current app has no existing REST API for most UI flows, so backend shaping is part of the migration

## Out Of Scope

The following are not part of this redesign:

- changing the database engine
- changing the downloader strategy
- changing PDF storage layout
- redesigning the core search/downloader algorithms
- multi-user auth
- remote deployment architecture

## Recommendation

Proceed with a phased Reflex migration using the two-column research workbench design. Prioritize Search and Library first, because they define the daily feel of the product. Only remove NiceGUI after the Reflex workflows and API surface are proven stable.
