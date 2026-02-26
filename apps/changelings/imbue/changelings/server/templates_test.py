from imbue.changelings.primitives import ChangelingName
from imbue.changelings.primitives import OneTimeCode
from imbue.changelings.server.templates import render_auth_error_page
from imbue.changelings.server.templates import render_landing_page
from imbue.changelings.server.templates import render_login_redirect_page


def test_render_landing_page_with_agents_lists_them_as_links() -> None:
    names = (ChangelingName("elena-turing"), ChangelingName("code-reviewer"))
    html = render_landing_page(accessible_changeling_names=names)
    assert "/agents/elena-turing/" in html
    assert "/agents/code-reviewer/" in html
    assert "elena-turing" in html
    assert "code-reviewer" in html


def test_render_landing_page_with_no_agents_shows_empty_state() -> None:
    html = render_landing_page(accessible_changeling_names=())
    assert "No changelings are accessible" in html
    assert "/agents/" not in html


def test_render_login_redirect_page_contains_redirect_script() -> None:
    html = render_login_redirect_page(
        changeling_name=ChangelingName("elena-turing"),
        one_time_code=OneTimeCode("abc123-secret-82341"),
    )
    assert "window.location.href" in html
    assert "changeling_name=elena-turing" in html
    assert "one_time_code=abc123-secret-82341" in html


def test_render_auth_error_page_shows_error_message() -> None:
    html = render_auth_error_page(message="This code has already been used.")
    assert "This code has already been used." in html
    assert "Authentication Failed" in html
    assert "generate a new login URL" in html


def test_render_landing_page_escapes_html_in_changeling_names() -> None:
    names = (ChangelingName("<script>alert(1)</script>"),)
    html = render_landing_page(accessible_changeling_names=names)
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html
