from collections.abc import Sequence
from typing import Final

from jinja2 import Environment
from jinja2 import select_autoescape

from imbue.changelings.primitives import ChangelingName
from imbue.changelings.primitives import OneTimeCode
from imbue.imbue_common.pure import pure

_JINJA_ENV: Final[Environment] = Environment(autoescape=select_autoescape(default=True))

_LANDING_PAGE_TEMPLATE: Final[str] = """<!DOCTYPE html>
<html>
<head>
  <title>Changelings</title>
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body { font-family: system-ui, -apple-system, sans-serif; padding: 40px; background: #f5f5f5; }
    h1 { margin-bottom: 24px; color: #1a1a2e; }
    .agent-list { list-style: none; }
    .agent-list li { margin-bottom: 8px; }
    .agent-list a {
      display: inline-block; padding: 12px 20px;
      background: #1a1a2e; color: white; text-decoration: none;
      border-radius: 6px; font-size: 16px;
    }
    .agent-list a:hover { background: #2a2a4e; }
    .empty-state { color: #666; font-size: 16px; }
  </style>
</head>
<body>
  <h1>Your Changelings</h1>
  {% if changeling_names %}
  <ul class="agent-list">
    {% for name in changeling_names %}
    <li><a href="/agents/{{ name }}/">{{ name }}</a></li>
    {% endfor %}
  </ul>
  {% else %}
  <p class="empty-state">
    No changelings are accessible. Use a login link to authenticate with a changeling.
  </p>
  {% endif %}
</body>
</html>"""

_LOGIN_REDIRECT_TEMPLATE: Final[str] = """<!DOCTYPE html>
<html>
<head><title>Authenticating...</title></head>
<body>
<p>Authenticating...</p>
<script>
window.location.href = '/authenticate?changeling_name={{ changeling_name }}&one_time_code={{ one_time_code }}';
</script>
</body>
</html>"""

_AUTH_ERROR_TEMPLATE: Final[str] = """<!DOCTYPE html>
<html>
<head>
  <title>Authentication Error</title>
  <style>
    body { font-family: system-ui, -apple-system, sans-serif; padding: 40px; background: #f5f5f5; }
    .error { background: #fee; border: 1px solid #fcc; padding: 20px; border-radius: 6px; color: #900; }
  </style>
</head>
<body>
  <div class="error">
    <h2>Authentication Failed</h2>
    <p>{{ message }}</p>
    <p>Please generate a new login URL for this device. Each login URL can only be used once.</p>
  </div>
</body>
</html>"""


@pure
def render_landing_page(accessible_changeling_names: Sequence[ChangelingName]) -> str:
    """Render the landing page listing accessible changelings."""
    template = _JINJA_ENV.from_string(_LANDING_PAGE_TEMPLATE)
    return template.render(changeling_names=accessible_changeling_names)


@pure
def render_login_redirect_page(
    changeling_name: ChangelingName,
    one_time_code: OneTimeCode,
) -> str:
    """Render the JS redirect page that forwards to /authenticate."""
    template = _JINJA_ENV.from_string(_LOGIN_REDIRECT_TEMPLATE)
    return template.render(changeling_name=changeling_name, one_time_code=one_time_code)


@pure
def render_auth_error_page(message: str) -> str:
    """Render an error page for failed authentication."""
    template = _JINJA_ENV.from_string(_AUTH_ERROR_TEMPLATE)
    return template.render(message=message)
