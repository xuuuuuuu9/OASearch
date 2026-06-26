# Reflex Workbench Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the NiceGUI frontend with a Reflex research workbench while preserving the existing FastAPI, SQLite, downloader, and PDF serving logic.

**Architecture:** Extract JSON API endpoints from the current UI-coupled FastAPI logic, then build a separate Reflex app that consumes those endpoints through page-focused state modules and a shared workbench shell. Keep the old NiceGUI pages only until the Reflex routes and backend APIs are verified.

**Tech Stack:** FastAPI, SQLite, Reflex, pytest, uv

## Global Constraints

- Keep the existing FastAPI backend, SQLite database, download engine, and PDF file routing.
- Build a two-column research workbench UI, not a marketing page or generic SaaS dashboard.
- Prioritize Search and Library before Downloads and Journals.
- Preserve current downloader, PDF storage, and search logic.
- Use TDD for behavior changes and new features.

---

### Task 1: Backend API Surface

**Files:**
- Create: `app/routers/api.py`
- Modify: `app/main.py`
- Modify: `app/repo.py`
- Test: `tests/test_api_routes.py`

**Interfaces:**
- Consumes: `repo.list_journals`, `repo.search_local`, `repo.create_search_task`, `repo.get_search_task`, `repo.get_search_task_papers`, `repo.list_tasks`, `repo.get_task`
- Produces: `/api/journals`, `/api/library/search`, `/api/search-tasks`, `/api/download-tasks` JSON endpoints

- [ ] Write failing API tests for journals listing, library search, latest search task, and download task detail.
- [ ] Run the focused API tests and confirm they fail because the router is missing.
- [ ] Add the API router with minimal Pydantic-friendly JSON responses using existing repo helpers.
- [ ] Register the router in `app/main.py` and rerun the focused API tests until they pass.

### Task 2: Search And Download Mutation APIs

**Files:**
- Modify: `app/routers/api.py`
- Modify: `app/models.py`
- Test: `tests/test_api_routes.py`

**Interfaces:**
- Consumes: `SearchRequest`, `repo.create_download_task`, `repo.update_search_task`, `retry_failed_items`
- Produces: `POST /api/search-tasks`, `POST /api/download-tasks`, `POST /api/download-tasks/{id}/retry`, `POST /api/download-tasks/{id}/items/{doi}/retry`

- [ ] Write failing tests for creating a search task, creating a download task, retrying a task, and retrying one failed DOI.
- [ ] Run the focused test selection and confirm the failures are for missing endpoints or response shape.
- [ ] Implement the minimal mutation endpoints, using existing background task behavior where appropriate.
- [ ] Rerun the focused mutation tests and then the full backend test suite.

### Task 3: Reflex App Scaffold

**Files:**
- Create: `rxconfig.py`
- Create: `frontend/__init__.py`
- Create: `frontend/app.py`
- Create: `frontend/theme.py`
- Create: `frontend/components/shell.py`
- Modify: `requirements.txt`
- Test: `tests/test_reflex_smoke.py`

**Interfaces:**
- Consumes: FastAPI backend base URL and Reflex route system
- Produces: a bootable Reflex app shell with page registration

- [ ] Write a failing smoke test that checks the Reflex app module imports and exposes the expected app object.
- [ ] Run the smoke test and confirm it fails because the Reflex scaffold does not exist.
- [ ] Add the Reflex dependency and create the minimal app, theme, and shell modules.
- [ ] Rerun the smoke test and verify the Reflex scaffold imports cleanly.

### Task 4: Reflex Search And Library Pages

**Files:**
- Create: `frontend/state/search_state.py`
- Create: `frontend/state/library_state.py`
- Create: `frontend/pages/search.py`
- Create: `frontend/pages/library.py`
- Create: `frontend/components/results.py`
- Modify: `frontend/app.py`
- Test: `tests/test_reflex_smoke.py`

**Interfaces:**
- Consumes: backend `/api/journals`, `/api/search-tasks`, `/api/library/search`
- Produces: Search and Library Reflex routes with workbench layout

- [ ] Write failing smoke tests that assert the Search and Library page modules import and register route callables.
- [ ] Run the smoke tests and confirm they fail for missing pages or state modules.
- [ ] Implement the Search and Library Reflex state and pages with dense workbench layout and API-backed actions.
- [ ] Rerun the smoke tests and manually verify the pages render.

### Task 5: Reflex Downloads And Journals Pages

**Files:**
- Create: `frontend/state/downloads_state.py`
- Create: `frontend/state/journals_state.py`
- Create: `frontend/pages/downloads.py`
- Create: `frontend/pages/journals.py`
- Modify: `frontend/app.py`
- Test: `tests/test_reflex_smoke.py`

**Interfaces:**
- Consumes: backend `/api/download-tasks`, `/api/journals`
- Produces: Downloads and Journals Reflex routes with mutation workflows

- [ ] Write failing smoke tests that assert the Downloads and Journals route modules import and expose page builders.
- [ ] Run the smoke tests and confirm they fail for missing routes.
- [ ] Implement the two remaining workbench pages and their state modules.
- [ ] Rerun the smoke tests and verify route imports pass.

### Task 6: Remove NiceGUI Runtime And Verify End-To-End

**Files:**
- Modify: `app/main.py`
- Modify: `README.md`
- Modify: `tests/test_ui_compat.py`
- Modify: `tests/test_ui_theme.py`
- Test: `tests/test_api_routes.py`
- Test: `tests/test_reflex_smoke.py`

**Interfaces:**
- Consumes: completed FastAPI JSON APIs and Reflex app entrypoint
- Produces: backend without NiceGUI runtime as the active frontend

- [ ] Write or update failing tests that enforce the active frontend is no longer NiceGUI-driven.
- [ ] Run the targeted tests and confirm the expected failures.
- [ ] Remove NiceGUI page registration from the active runtime, document the new Reflex startup flow, and keep PDF routes working.
- [ ] Run the full test suite, then boot the app and verify the Reflex UI in the browser on desktop and mobile.
