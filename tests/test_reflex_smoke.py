from __future__ import annotations


def test_reflex_app_module_exposes_app() -> None:
    from frontend.app import app

    assert app is not None
    assert app.__class__.__name__ == "App"


def test_reflex_page_modules_export_builders() -> None:
    from frontend.pages import downloads, journals, library, search
    from frontend.state import downloads_state, journals_state, library_state, search_state

    assert callable(search.search_page)
    assert callable(library.library_page)
    assert callable(downloads.downloads_page)
    assert callable(journals.journals_page)
    assert search_state.SearchState.__name__ == "SearchState"
    assert library_state.LibraryState.__name__ == "LibraryState"
    assert downloads_state.DownloadsState.__name__ == "DownloadsState"
    assert journals_state.JournalsState.__name__ == "JournalsState"
