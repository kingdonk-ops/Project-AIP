"""A tiny headless "browser" for the Keycloak login pages (tests only).

It follows redirects by hand, stops at the app's callback URL (never requesting it, as a browser
would hand it to the app), and fills the forms Keycloak renders.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from html.parser import HTMLParser
from urllib.parse import urljoin

import httpx


@dataclass
class Form:
    action: str
    method: str
    fields: dict[str, str] = field(default_factory=dict[str, str])
    inputs: set[str] = field(default_factory=set[str])


class _FormParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.forms: list[Form] = []
        self._current: Form | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = {k: v or "" for k, v in attrs}
        if tag == "form":
            self._current = Form(action=a.get("action", ""), method=a.get("method", "get").lower())
            self.forms.append(self._current)
        elif tag in ("input", "button") and self._current is not None and a.get("name"):
            name = a["name"]
            self._current.inputs.add(name)
            kind = a.get("type", "text").lower()
            if kind in ("hidden", "text", "email") and name not in self._current.fields:
                self._current.fields[name] = a.get("value", "")

    def handle_endtag(self, tag: str) -> None:
        if tag == "form":
            self._current = None


def forms(html: str) -> list[Form]:
    parser = _FormParser()
    parser.feed(html)
    return parser.forms


@dataclass
class Page:
    url: str
    html: str

    def form_with(self, name: str) -> Form | None:
        return next((f for f in forms(self.html) if name in f.inputs), None)


class Browser:
    def __init__(self, stop_prefix: str) -> None:
        self.stop_prefix = stop_prefix
        self.client = httpx.Client(timeout=30)
        self.visited: list[str] = []
        self.pages: list[Page] = []

    def close(self) -> None:
        self.client.close()

    def _insecure_cookies(self) -> None:
        # Keycloak marks its cookies Secure; the test servers speak plain http on localhost,
        # where real browsers still send them (localhost is a secure context). Do the same.
        for cookie in self.client.cookies.jar:
            cookie.secure = False

    def _follow(self, response: httpx.Response) -> Page | str:
        for _ in range(30):
            self._insecure_cookies()
            if response.is_redirect:
                location = urljoin(str(response.url), response.headers["location"])
                self.visited.append(location)
                if location.startswith(self.stop_prefix):
                    return location
                response = self.client.get(location)
                continue
            page = Page(str(response.url), response.text)
            self.pages.append(page)
            return page
        raise RuntimeError("too many redirects")

    def get(self, url: str) -> Page | str:
        self.visited.append(url)
        self._insecure_cookies()
        return self._follow(self.client.get(url))

    def submit(self, page: Page, form: Form, values: dict[str, str]) -> Page | str:
        data = {**form.fields, **values}
        action = urljoin(page.url, form.action)
        self._insecure_cookies()
        return self._follow(self.client.post(action, data=data))


Filler = Callable[[Page], "dict[str, str] | None"]


def drive(browser: Browser, start: Page | str, fill: Filler, max_steps: int = 10) -> Page | str:
    """Fill pages until the callback URL is reached or ``fill`` returns None (stop on a page)."""
    current = start
    for _ in range(max_steps):
        if isinstance(current, str):
            return current
        values = fill(current)
        if values is None:
            return current
        form = next((f for f in forms(current.html) if set(values) <= f.inputs), None)
        if form is None:
            raise AssertionError(f"no form for {sorted(values)} at {current.url}")
        current = browser.submit(current, form, values)
    return current
