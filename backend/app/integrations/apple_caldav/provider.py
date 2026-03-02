"""
Apple CalDAV integration provider.

Uses CalDAV (RFC 4791) with HTTP Basic Authentication.
Credentials are stored in ProviderContext.extra_config:
    {"username": "...", "password": "...", "caldav_url": "https://caldav.icloud.com"}

The caldav_url defaults to Apple's iCloud CalDAV server.
"""

from __future__ import annotations

import base64
import re
import uuid
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

import httpx

from app.integrations.base import (
    IntegrationProvider,
    NormalisedEvent,
    ProviderContext,
    TokenData,
)
from app.integrations.apple_caldav.mapper import (
    normalised_to_ical,
    parse_ical_events,
    vevent_to_normalised,
)
from app.integrations.registry import register

_APPLE_CALDAV_BASE = "https://caldav.icloud.com"
_NS_DAV = "DAV:"
_NS_CAL = "urn:ietf:params:xml:ns:caldav"

ET.register_namespace("D", _NS_DAV)
ET.register_namespace("C", _NS_CAL)


@register("apple_caldav")
class AppleCalDAVProvider(IntegrationProvider):
    """Reads and writes events on an Apple Calendar (iCloud) via CalDAV."""

    def __init__(self, context: ProviderContext) -> None:
        super().__init__(context)
        self._username: str = context.extra_config.get("username", "")
        self._password: str = context.extra_config.get("password", "")
        self._caldav_url: str = context.extra_config.get(
            "caldav_url", _APPLE_CALDAV_BASE
        ).rstrip("/")
        # Cached calendar path — discovered on first use
        self._calendar_path: str | None = context.extra_config.get("calendar_path")

    @property
    def provider_name(self) -> str:
        return "apple_caldav"

    @property
    def provider_type(self) -> str:
        return "calendar"

    # ── Auth helpers ──────────────────────────────────────────────────────────

    def _basic_auth(self) -> str:
        creds = f"{self._username}:{self._password}"
        return "Basic " + base64.b64encode(creds.encode()).decode()

    def _xml_headers(self) -> dict[str, str]:
        return {
            "Authorization": self._basic_auth(),
            "Content-Type": "application/xml; charset=utf-8",
        }

    def _ical_headers(self) -> dict[str, str]:
        return {
            "Authorization": self._basic_auth(),
            "Content-Type": "text/calendar; charset=utf-8",
        }

    # ── CalDAV discovery ──────────────────────────────────────────────────────

    async def _discover_calendar_path(self, client: httpx.AsyncClient) -> str:
        """
        Three-step CalDAV discovery:
        1. PROPFIND /  → current-user-principal href
        2. PROPFIND principal → calendar-home-set href
        3. PROPFIND home-set depth:1 → find first VEVENT-capable calendar
        """
        # Step 1: current-user-principal
        body1 = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<D:propfind xmlns:D="DAV:">'
            "<D:prop><D:current-user-principal/></D:prop>"
            "</D:propfind>"
        )
        r1 = await client.request(
            "PROPFIND",
            f"{self._caldav_url}/",
            headers={**self._xml_headers(), "Depth": "0"},
            content=body1.encode(),
        )
        r1.raise_for_status()
        principal = _find_tag_text(
            r1.text, f"{{{_NS_DAV}}}current-user-principal", f"{{{_NS_DAV}}}href"
        )
        if not principal:
            principal = f"/principals/{self._username}/"

        # Step 2: calendar-home-set
        body2 = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            f'<D:propfind xmlns:D="DAV:" xmlns:C="{_NS_CAL}">'
            "<D:prop><C:calendar-home-set/></D:prop>"
            "</D:propfind>"
        )
        base = _base_url(self._caldav_url)
        r2 = await client.request(
            "PROPFIND",
            f"{base}{principal}",
            headers={**self._xml_headers(), "Depth": "0"},
            content=body2.encode(),
        )
        r2.raise_for_status()
        home = _find_tag_text(
            r2.text, f"{{{_NS_CAL}}}calendar-home-set", f"{{{_NS_DAV}}}href"
        )
        if not home:
            home = f"/calendars/{self._username}/"

        # Step 3: list calendars and pick first VEVENT-capable one
        body3 = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            f'<D:propfind xmlns:D="DAV:" xmlns:C="{_NS_CAL}">'
            "<D:prop>"
            "<D:resourcetype/>"
            "<C:supported-calendar-component-set/>"
            "</D:prop>"
            "</D:propfind>"
        )
        r3 = await client.request(
            "PROPFIND",
            f"{base}{home}",
            headers={**self._xml_headers(), "Depth": "1"},
            content=body3.encode(),
        )
        r3.raise_for_status()
        cal_path = _find_vevent_calendar(r3.text, home)
        return cal_path or home

    async def _get_calendar_path(self, client: httpx.AsyncClient) -> str:
        if not self._calendar_path:
            self._calendar_path = await self._discover_calendar_path(client)
        return self._calendar_path

    # ── IntegrationProvider interface ─────────────────────────────────────────

    async def fetch_events(self, start: datetime, end: datetime) -> list[NormalisedEvent]:
        async with httpx.AsyncClient(timeout=30.0) as client:
            cal_path = await self._get_calendar_path(client)
            base = _base_url(self._caldav_url)
            start_str = start.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            end_str = end.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

            report_body = (
                '<?xml version="1.0" encoding="UTF-8"?>'
                f'<C:calendar-query xmlns:D="DAV:" xmlns:C="{_NS_CAL}">'
                "<D:prop><D:getetag/><C:calendar-data/></D:prop>"
                "<C:filter>"
                '<C:comp-filter name="VCALENDAR">'
                '<C:comp-filter name="VEVENT">'
                f'<C:time-range start="{start_str}" end="{end_str}"/>'
                "</C:comp-filter>"
                "</C:comp-filter>"
                "</C:filter>"
                "</C:calendar-query>"
            )
            resp = await client.request(
                "REPORT",
                f"{base}{cal_path}",
                headers={**self._xml_headers(), "Depth": "1"},
                content=report_body.encode(),
            )
            resp.raise_for_status()

        events: list[NormalisedEvent] = []
        for ical_text in _extract_calendar_data(resp.text):
            for uid, vevent in parse_ical_events(ical_text):
                events.append(vevent_to_normalised(vevent, source_id=uid))
        return events

    async def create_event(self, event: NormalisedEvent) -> str:
        async with httpx.AsyncClient(timeout=30.0) as client:
            cal_path = await self._get_calendar_path(client)
            base = _base_url(self._caldav_url)
            event_uid = str(uuid.uuid4())
            ical_bytes = normalised_to_ical(event, uid=event_uid)
            resp = await client.put(
                f"{base}{cal_path}{event_uid}.ics",
                headers=self._ical_headers(),
                content=ical_bytes,
            )
            resp.raise_for_status()
        return event_uid

    async def update_event(self, provider_event_id: str, event: NormalisedEvent) -> None:
        async with httpx.AsyncClient(timeout=30.0) as client:
            cal_path = await self._get_calendar_path(client)
            base = _base_url(self._caldav_url)
            ical_bytes = normalised_to_ical(event, uid=provider_event_id)
            resp = await client.put(
                f"{base}{cal_path}{provider_event_id}.ics",
                headers=self._ical_headers(),
                content=ical_bytes,
            )
            resp.raise_for_status()

    async def delete_event(self, provider_event_id: str) -> None:
        async with httpx.AsyncClient(timeout=30.0) as client:
            cal_path = await self._get_calendar_path(client)
            base = _base_url(self._caldav_url)
            resp = await client.delete(
                f"{base}{cal_path}{provider_event_id}.ics",
                headers={"Authorization": self._basic_auth()},
            )
            resp.raise_for_status()

    # ── OAuth (not supported — CalDAV uses Basic Auth) ────────────────────────

    @classmethod
    def get_oauth_url(cls, state: str, redirect_uri: str) -> str:
        raise NotImplementedError("Apple CalDAV uses Basic Auth, not OAuth")

    @classmethod
    async def exchange_code(cls, code: str, redirect_uri: str) -> TokenData:
        raise NotImplementedError("Apple CalDAV uses Basic Auth, not OAuth")


# ── XML helpers ───────────────────────────────────────────────────────────────


def _base_url(url: str) -> str:
    """Return scheme://host from a URL."""
    from urllib.parse import urlparse

    p = urlparse(url)
    return f"{p.scheme}://{p.netloc}"


def _find_tag_text(xml_text: str, parent_tag: str, child_tag: str) -> str | None:
    """
    Search an XML multistatus response for a <parent_tag><child_tag>text</child_tag>
    structure and return the text content of the first match.
    """
    try:
        root = ET.fromstring(xml_text)
        for parent in root.iter(parent_tag):
            child = parent.find(child_tag)
            if child is not None and child.text:
                return child.text.strip()
        # Fallback: look for child tag anywhere
        for child in root.iter(child_tag):
            if child.text:
                return child.text.strip()
    except ET.ParseError:
        pass
    return None


def _find_vevent_calendar(xml_text: str, home_href: str) -> str | None:
    """
    Parse PROPFIND multistatus to find the first calendar collection that
    supports VEVENT components. Returns its href path or None.
    """
    try:
        root = ET.fromstring(xml_text)
        for response in root.iter(f"{{{_NS_DAV}}}response"):
            href_el = response.find(f".//{{{_NS_DAV}}}href")
            if href_el is None or not href_el.text:
                continue
            href = href_el.text.strip()
            # Skip the home collection itself
            if href.rstrip("/") == home_href.rstrip("/"):
                continue
            # Must have calendar resourcetype
            rt = response.find(f".//{{{_NS_DAV}}}resourcetype")
            if rt is None or rt.find(f"{{{_NS_CAL}}}calendar") is None:
                continue
            # Must support VEVENT (if the server declares component sets)
            comp_set = response.find(f".//{{{_NS_CAL}}}supported-calendar-component-set")
            if comp_set is not None:
                comp_names = [c.get("name", "") for c in comp_set.iter(f"{{{_NS_CAL}}}comp")]
                if "VEVENT" not in comp_names:
                    continue
            return href
    except ET.ParseError:
        pass
    return None


def _extract_calendar_data(xml_text: str) -> list[str]:
    """Extract all <C:calendar-data> text blocks from a REPORT multistatus response."""
    try:
        root = ET.fromstring(xml_text)
        results = []
        for cd in root.iter(f"{{{_NS_CAL}}}calendar-data"):
            if cd.text:
                results.append(cd.text.strip())
        return results
    except ET.ParseError:
        # Fallback regex for malformed XML
        pattern = r"<[^/>]*:calendar-data[^>]*>(.*?)</[^/>]*:calendar-data>"
        matches = re.findall(pattern, xml_text, re.DOTALL)
        return [m.strip() for m in matches if m.strip()]
