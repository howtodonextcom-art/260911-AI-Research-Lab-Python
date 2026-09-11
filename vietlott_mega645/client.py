from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import json
import re
import time
from pathlib import Path
from typing import Iterable, Iterator
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen

BASE_URL = "https://vietlott.vn"
LATEST_PATH = "/vi/trung-thuong/ket-qua-trung-thuong/645?nocatche=1"
DETAIL_PATH = "/vi/trung-thuong/ket-qua-trung-thuong/645?id={draw_id}&nocatche=1"
HISTORY_PATH = "/vi/trung-thuong/ket-qua-trung-thuong/winning-number-645"
AJAX_COMPARE_PATH = "/ajaxpro/Vietlott.PlugIn.WebParts.Game645CompareWebPart,Vietlott.PlugIn.WebParts.ashx"

DEFAULT_USER_AGENT = "mega645-research-lab-python-poc/0.1 (+https://vietlott.vn)"
DEFAULT_TIMEOUT_SECONDS = 20
DEFAULT_MAX_RESPONSE_BYTES = 5 * 1024 * 1024
DRAW_SIZE = 6
MIN_NUMBER = 1
MAX_NUMBER = 45


class VietlottMega645Error(Exception):
    """Base class for package errors."""


class FetchError(VietlottMega645Error):
    """Raised when a public Vietlott page cannot be fetched."""


class ParseError(VietlottMega645Error):
    """Raised when a page does not match the expected public HTML shape."""


class ValidationError(VietlottMega645Error):
    """Raised when a parsed draw violates Mega 6/45 invariants."""


@dataclass(frozen=True, slots=True)
class DrawRecord:
    date: str
    id: str
    result: tuple[int, ...]
    source_url: str | None = None

    def __post_init__(self) -> None:
        normalized = tuple(sorted(int(number) for number in self.result))
        object.__setattr__(self, "result", normalized)
        validate_draw(self.date, self.id, normalized)

    def to_dict(self, include_source: bool = False) -> dict[str, object]:
        row: dict[str, object] = {
            "date": self.date,
            "id": self.id,
            "result": list(self.result),
        }
        if include_source and self.source_url:
            row["source_url"] = self.source_url
        return row


def validate_draw(iso_date: str, draw_id: str, result: Iterable[int]) -> None:
    try:
        date.fromisoformat(iso_date)
    except ValueError as exc:
        raise ValidationError(f"Invalid date: {iso_date}") from exc

    if not re.fullmatch(r"\d{5}", draw_id):
        raise ValidationError(f"Draw id must be five digits: {draw_id!r}")

    numbers = list(result)
    if len(numbers) != DRAW_SIZE:
        raise ValidationError(f"Expected {DRAW_SIZE} numbers, got {len(numbers)}")
    if len(set(numbers)) != DRAW_SIZE:
        raise ValidationError("Draw numbers must be distinct")
    for number in numbers:
        if not isinstance(number, int) or number < MIN_NUMBER or number > MAX_NUMBER:
            raise ValidationError(f"Number out of Mega 6/45 range: {number!r}")


def parse_vietnamese_date(value: str) -> str:
    match = re.fullmatch(r"(\d{2})/(\d{2})/(\d{4})", value.strip())
    if not match:
        raise ParseError(f"Expected DD/MM/YYYY date, got {value!r}")
    day, month, year = map(int, match.groups())
    return date(year, month, day).isoformat()


def _parse_ball_numbers(html_fragment: str) -> tuple[int, ...]:
    numbers = [
        int(match.group(1))
        for match in re.finditer(
            r'<span[^>]*class="[^"]*\bbong_tron\b[^"]*"[^>]*>\s*(\d{1,2})\s*</span>',
            html_fragment,
            flags=re.IGNORECASE,
        )
    ]
    if len(numbers) != DRAW_SIZE:
        raise ParseError(f"Expected {DRAW_SIZE} result balls, got {len(numbers)}")
    return tuple(numbers)


def parse_detail_html(html: str, source_url: str | None = None) -> DrawRecord:
    header = re.search(
        r"Kỳ\s+quay\s+thưởng\s*<b>#(?P<id>\d{5})</b>\s*ngày\s*<b>(?P<date>\d{2}/\d{2}/\d{4})</b>",
        html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not header:
        raise ParseError("Could not find Mega 6/45 draw id/date in detail page")

    block = re.search(
        r'<div\s+class="day_so_ket_qua_v2"[^>]*>(?P<body>.*?)</div>',
        html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not block:
        raise ParseError("Could not find result ball block in detail page")

    return DrawRecord(
        date=parse_vietnamese_date(header.group("date")),
        id=header.group("id"),
        result=_parse_ball_numbers(block.group("body")),
        source_url=source_url,
    )


_HISTORY_ROW_RE = re.compile(
    r"<tr>\s*"
    r"<td>\s*(?P<date>\d{2}/\d{2}/\d{4})\s*</td>\s*"
    r"<td>\s*<a\s+href=\"(?P<href>[^\"]*?id=(?P<id>\d{5})&nocatche=1[^\"]*)\"[^>]*>\s*\d{5}\s*</a>\s*</td>\s*"
    r"<td>(?P<numbers>.*?)</td>\s*"
    r"</tr>",
    flags=re.IGNORECASE | re.DOTALL,
)


def parse_history_html(html: str, source_url: str | None = None) -> list[DrawRecord]:
    rows: list[DrawRecord] = []
    for match in _HISTORY_ROW_RE.finditer(html):
        href = match.group("href")
        absolute_url = urljoin(source_url or BASE_URL, href)
        rows.append(
            DrawRecord(
                date=parse_vietnamese_date(match.group("date")),
                id=match.group("id"),
                result=_parse_ball_numbers(match.group("numbers")),
                source_url=absolute_url,
            )
        )
    return rows


def discover_history_key(html: str) -> str:
    match = re.search(
        r"Game645CompareWebPart\.ServerSideDrawResult\(RenderInfo,\s*'(?P<key>[^']+)'",
        html,
        flags=re.IGNORECASE,
    )
    if not match:
        raise ParseError("Could not discover Vietlott AjaxPro history key")
    return match.group("key")


def serialize_jsonl(records: Iterable[DrawRecord], include_source: bool = False) -> str:
    ordered = sorted(records, key=lambda record: (record.date, record.id))
    return "".join(
        json.dumps(record.to_dict(include_source=include_source), ensure_ascii=False, separators=(",", ":")) + "\n"
        for record in ordered
    )


def write_jsonl(path: str | Path, records: Iterable[DrawRecord], include_source: bool = False) -> None:
    Path(path).write_text(serialize_jsonl(records, include_source=include_source), encoding="utf-8")


class VietlottMega645Client:
    def __init__(
        self,
        base_url: str = BASE_URL,
        *,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
        max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES,
        user_agent: str = DEFAULT_USER_AGENT,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.max_response_bytes = max_response_bytes
        self.user_agent = user_agent

    def fetch_latest(self) -> DrawRecord:
        url = self._url(LATEST_PATH)
        return parse_detail_html(self._get_text(url), source_url=url)

    def fetch_draw(self, draw_id: str) -> DrawRecord:
        if not re.fullmatch(r"\d{5}", draw_id):
            raise ValidationError(f"Draw id must be five digits: {draw_id!r}")
        url = self._url(DETAIL_PATH.format(draw_id=draw_id))
        return parse_detail_html(self._get_text(url), source_url=url)

    def fetch_history_page(self, page_index: int, *, key: str | None = None) -> list[DrawRecord]:
        if page_index < 0:
            raise ValueError("page_index must be >= 0")
        landing_html = None
        if key is None:
            landing_html = self._get_text(self._url(HISTORY_PATH))
            key = discover_history_key(landing_html)
        if page_index == 0 and landing_html is not None:
            return parse_history_html(landing_html, source_url=self._url(HISTORY_PATH))
        html = self._post_history_page(page_index, key)
        return parse_history_html(html, source_url=self._url(HISTORY_PATH))

    def iter_history(
        self,
        *,
        max_pages: int | None = None,
        delay_seconds: float = 0.5,
    ) -> Iterator[DrawRecord]:
        if max_pages is not None and max_pages < 1:
            return

        landing_url = self._url(HISTORY_PATH)
        landing_html = self._get_text(landing_url)
        key = discover_history_key(landing_html)
        seen_ids: set[str] = set()
        page_index = 0

        while max_pages is None or page_index < max_pages:
            if page_index == 0:
                html = landing_html
            else:
                html = self._post_history_page(page_index, key)

            records = parse_history_html(html, source_url=landing_url)
            fresh = [record for record in records if record.id not in seen_ids]
            if not fresh:
                break

            for record in fresh:
                seen_ids.add(record.id)
                yield record

            if len(records) < 8:
                break
            page_index += 1
            if max_pages is None or page_index < max_pages:
                time.sleep(delay_seconds)

    def fetch_history(self, *, max_pages: int | None = None, delay_seconds: float = 0.5) -> list[DrawRecord]:
        return list(self.iter_history(max_pages=max_pages, delay_seconds=delay_seconds))

    def _url(self, path_or_url: str) -> str:
        if path_or_url.startswith("http://") or path_or_url.startswith("https://"):
            return path_or_url
        return urljoin(f"{self.base_url}/", path_or_url.lstrip("/"))

    def _get_text(self, url: str) -> str:
        request = Request(
            url,
            headers={
                "User-Agent": self.user_agent,
                "Accept": "text/html,application/xhtml+xml",
            },
        )
        return self._read_text(request)

    def _post_history_page(self, page_index: int, key: str) -> str:
        body = {
            "ORenderInfo": {
                "SiteId": "main.frontend.vi",
                "SiteAlias": "main.vi",
                "UserSessionId": "",
                "SiteLang": "vi",
                "IsPageDesign": False,
                "ExtraParam1": "",
                "ExtraParam2": "",
                "ExtraParam3": "",
                "SiteURL": "",
                "WebPage": None,
                "SiteName": "Vietlott",
                "OrgPageAlias": None,
                "PageAlias": None,
                "FullPageAlias": None,
                "RefKey": None,
                "System": 1,
            },
            "Key": key,
            "GameDrawId": "",
            "ArrayNumbers": [[""] * 18 for _ in range(6)],
            "CheckMulti": False,
            "PageIndex": page_index,
        }
        request = Request(
            self._url(AJAX_COMPARE_PATH),
            data=json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
            headers={
                "User-Agent": self.user_agent,
                "Accept": "application/json,text/plain,*/*",
                "Content-Type": "text/plain; charset=utf-8",
                "X-AjaxPro-Method": "ServerSideDrawResult",
            },
            method="POST",
        )
        payload = json.loads(self._read_text(request))
        if payload.get("error"):
            raise FetchError(f"AjaxPro error: {payload['error']}")
        value = payload.get("value")
        if not isinstance(value, dict) or value.get("Error"):
            message = value.get("InfoMessage") if isinstance(value, dict) else None
            raise FetchError(f"Vietlott history endpoint returned an error: {message or payload!r}")
        html = value.get("HtmlContent")
        if not isinstance(html, str):
            raise ParseError("Vietlott history response did not contain HtmlContent")
        return html

    def _read_text(self, request: Request) -> str:
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                body = response.read(self.max_response_bytes + 1)
                if len(body) > self.max_response_bytes:
                    raise FetchError(f"Response exceeded {self.max_response_bytes} bytes")
                charset = response.headers.get_content_charset() or "utf-8"
                return body.decode(charset, errors="replace")
        except HTTPError as exc:
            raise FetchError(f"HTTP {exc.code} while fetching {request.full_url}") from exc
        except URLError as exc:
            raise FetchError(f"Network error while fetching {request.full_url}: {exc.reason}") from exc
