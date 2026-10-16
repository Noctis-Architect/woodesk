from __future__ import annotations

import html as _html
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse

import httpx

from .. import __version__


class ApiError(Exception):
    def __init__(self, message: str, status: int | None = None, payload=None):
        super().__init__(message)
        self.message = message
        self.status = status
        self.payload = payload

    def __str__(self) -> str:
        return f"{self.message}" + (f" (HTTP {self.status})" if self.status else "")


def normalize_url(url: str) -> str:
    url = (url or "").strip()
    if not url:
        return ""
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url.rstrip("/")


def domain_of(url: str) -> str:
    return (urlparse(normalize_url(url)).hostname or "").lower()


def make_client(timeout: float = 30.0) -> httpx.Client:
    # One client per site/provider is reused, so TCP+TLS connections stay open (keep-alive).
    return httpx.Client(
        timeout=httpx.Timeout(timeout, connect=10.0),
        follow_redirects=True,
        headers={"User-Agent": f"WooDesk/{__version__}"},
        limits=httpx.Limits(max_connections=16, max_keepalive_connections=8, keepalive_expiry=60),
    )


def run_parallel(fns, workers: int = 4) -> list:
    """Run independent blocking callables concurrently (worker-thread use only); keeps order."""
    fns = list(fns)
    if len(fns) <= 1:
        return [f() for f in fns]
    with ThreadPoolExecutor(max_workers=min(workers, len(fns))) as ex:
        futures = [ex.submit(f) for f in fns]
        return [f.result() for f in futures]


def raise_for(resp: httpx.Response) -> None:
    if resp.status_code < 400:
        return
    message = f"HTTP {resp.status_code}"
    payload = None
    try:
        payload = resp.json()
        if isinstance(payload, dict):
            err = payload.get("message") or payload.get("detail") or payload.get("error")
            if isinstance(err, dict):
                err = err.get("message")
            if isinstance(err, list):
                err = "; ".join(str(x) for x in err)
            if err:
                message = str(err)
    except Exception:
        text = resp.text.strip()
        if text:
            message = text[:300]
    if resp.status_code == 401 or resp.status_code == 403:
        message = f"{message} - check credentials/permissions"
    raise ApiError(message, resp.status_code, payload)


class RestBase:
    """Shared behaviour for the WordPress and WooCommerce REST clients."""

    def __init__(self, base_url: str, auth: tuple[str, str] | None, prefix: str, client: httpx.Client | None = None):
        self.site = normalize_url(base_url)
        self.base = f"{self.site}/wp-json{prefix}"
        self.auth = auth if auth and auth[0] else None
        self.http = client or make_client()

    def request(self, method: str, path: str, **kw) -> httpx.Response:
        try:
            r = self.http.request(method, self.base + path, auth=self.auth, **kw)
        except httpx.HTTPError as e:
            raise ApiError(f"Connection failed: {e}") from e
        raise_for(r)
        return r

    def json(self, method: str, path: str, **kw):
        r = self.request(method, path, **kw)
        try:
            return r.json()
        except Exception as e:
            raise ApiError("Server did not return JSON (is the REST API blocked or the URL wrong?)") from e

    def page(self, path: str, params: dict | None = None) -> tuple[list, int, int]:
        r = self.request("GET", path, params=params)
        try:
            data = r.json()
        except Exception as e:
            raise ApiError("Server did not return JSON (is the REST API blocked or the URL wrong?)") from e
        total = int(r.headers.get("X-WP-Total", len(data) if isinstance(data, list) else 0))
        pages = int(r.headers.get("X-WP-TotalPages", 1))
        return data, total, pages

    def all_pages(self, path: str, params: dict | None = None, max_pages: int = 20) -> list:
        """Fetch every page of a collection. Page 1 tells us the page count; the rest load in parallel."""
        params = dict(params or {})
        params.setdefault("per_page", 100)
        params["page"] = 1
        data, _total, pages = self.page(path, params)
        out: list = list(data)
        pages = min(pages, max_pages)
        if pages > 1:
            rest = run_parallel([(lambda n=n: self.page(path, {**params, "page": n})[0]) for n in range(2, pages + 1)])
            for chunk in rest:
                out.extend(chunk)
        return out

    # ---- tags (same shape on /wp/v2/tags and /wc/v3/products/tags) -------------
    tags_path = "/tags"

    def create_tag(self, name: str) -> dict:  # overridden by subclasses
        raise NotImplementedError

    def find_tag(self, name: str) -> int | None:
        """Look a tag up by name with a server-side search (no need to download every tag)."""
        want = name.strip().lower()
        found = self.json("GET", self.tags_path, params={"search": name, "per_page": 100})
        for t in found if isinstance(found, list) else []:
            if _html.unescape(str(t.get("name", ""))).strip().lower() == want:
                return t["id"]
        return None

    def ensure_tags(self, names: list[str]) -> list[int]:
        ids: list[int] = []
        known: dict[str, int] = {}
        for n in names:
            n = n.strip()
            if not n:
                continue
            key = n.lower()
            if key not in known:
                tid = self.find_tag(n)
                if not tid:
                    tid = self.create_tag(n)["id"]
                known[key] = tid
            if known[key] not in ids:
                ids.append(known[key])
        return ids
