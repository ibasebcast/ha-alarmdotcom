"""Alarm.com camera session helpers using browser-style web requests."""

from __future__ import annotations

import json
import logging
from enum import Enum
from typing import Any

import aiohttp
from bs4 import BeautifulSoup

URL_BASE = "https://www.alarm.com/"
API_URL_BASE = URL_BASE + "web/api/"

MFA_COOKIE_KEY = "twoFactorAuthenticationId"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/123.0.0.0 Safari/537.36"
)
REFERER = "https://www.alarm.com/web/system/home"

VIEWSTATE_FIELD = "__VIEWSTATE"
VIEWSTATEGENERATOR_FIELD = "__VIEWSTATEGENERATOR"
EVENTVALIDATION_FIELD = "__EVENTVALIDATION"
PREVIOUSPAGE_FIELD = "__PREVIOUSPAGE"
TWO_FACTOR_PATH = "engines/twoFactorAuthentication/twoFactorAuthentications"

_LOGGER = logging.getLogger(__name__)


class OtpType(Enum):
    """MFA types supported by Alarm.com."""

    disabled = 0
    app = 1
    sms = 2
    email = 4


class AuthResult(Enum):
    """Result of an authentication attempt."""

    SUCCESS = "success"
    MFA_REQUIRED = "mfa_required"
    ERROR = "error"


ACCEPT_HTML = {"Accept": "text/html,application/xhtml+xml,application/xml"}
ACCEPT_JSON = {"Accept": "application/json", "charset": "utf-8"}
ACCEPT_JSONAPI = {"Accept": "application/vnd.api+json", "charset": "utf-8"}
CONTENT_FORM = {"Content-Type": "application/x-www-form-urlencoded", "charset": "utf-8"}


def _build_headers(
    accept: dict[str, str] | None = None,
    ajax_key: str | None = None,
) -> dict[str, str]:
    headers: dict[str, str] = {
        "User-Agent": USER_AGENT,
        "Referer": REFERER,
        "Connection": "keep-alive",
    }
    if accept:
        headers.update(accept)
    if ajax_key:
        headers["Ajaxrequestuniquekey"] = ajax_key
    return headers


class AlarmCameraSession:
    """Manages a browser-like Alarm.com session for camera APIs."""

    def __init__(
        self,
        username: str,
        password: str | None = None,
        *,
        ajax_key: str | None = None,
        mfa_cookie: str | None = None,
        identity_id: str | None = None,
    ) -> None:
        self.username = username
        self.password = password
        self.ajax_key = ajax_key
        self.mfa_cookie = mfa_cookie
        self.identity_id = identity_id
        self.cookie_jar = aiohttp.CookieJar(unsafe=True)
        self.session = aiohttp.ClientSession(cookie_jar=self.cookie_jar)
        self._pending_mfa_type: OtpType | None = None

    @property
    def session_data(self) -> dict[str, str | None]:
        """Return session metadata suitable for persistence."""
        return {
            "ajax_key": self.ajax_key,
            "mfa_cookie": self.mfa_cookie,
            "identity_id": self.identity_id,
        }

    def _extra_cookies(self) -> dict[str, str]:
        cookies: dict[str, str] = {}
        if self.mfa_cookie:
            cookies[MFA_COOKIE_KEY] = self.mfa_cookie
        return cookies

    def _extract_cookies(self, resp: aiohttp.ClientResponse) -> None:
        if afg := resp.cookies.get("afg"):
            self.ajax_key = afg.value
        if mfa := resp.cookies.get(MFA_COOKIE_KEY):
            if mfa.value != self.mfa_cookie:
                self.mfa_cookie = mfa.value

    async def _get(
        self,
        url: str,
        *,
        accept: dict[str, str] | None = None,
        use_ajax: bool = True,
    ) -> aiohttp.ClientResponse:
        resp = await self.session.get(
            url,
            headers=_build_headers(accept or ACCEPT_JSONAPI, self.ajax_key if use_ajax else None),
            cookies=self._extra_cookies(),
            allow_redirects=True,
        )
        self._extract_cookies(resp)
        resp.raise_for_status()
        return resp

    async def _post(
        self,
        url: str,
        *,
        accept: dict[str, str] | None = None,
        use_ajax: bool = True,
        data: dict | None = None,
        json_body: dict | None = None,
    ) -> aiohttp.ClientResponse:
        kwargs: dict[str, Any] = {
            "headers": _build_headers(accept or ACCEPT_JSONAPI, self.ajax_key if use_ajax else None),
            "cookies": self._extra_cookies(),
            "allow_redirects": True,
        }
        if data is not None:
            kwargs["data"] = data
        if json_body is not None:
            kwargs["json"] = json_body
        resp = await self.session.post(url, **kwargs)
        self._extract_cookies(resp)
        resp.raise_for_status()
        return resp

    async def login(self) -> AuthResult:
        """Perform full login flow."""
        if not self.password:
            raise ValueError("Password required for login")

        resp = await self._get(f"{URL_BASE}login", accept=ACCEPT_HTML, use_ajax=False)
        html = await resp.text()
        soup = BeautifulSoup(html, "html.parser")

        fields: dict[str, str] = {}
        for field_id in (
            VIEWSTATE_FIELD,
            VIEWSTATEGENERATOR_FIELD,
            EVENTVALIDATION_FIELD,
            PREVIOUSPAGE_FIELD,
        ):
            el = soup.select_one(f"#{field_id}")
            if el is None:
                raise RuntimeError(f"Could not find #{field_id} in login page HTML")
            fields[field_id] = str(el.attrs.get("value", ""))

        resp = await self._post(
            f"{URL_BASE}web/Default.aspx",
            accept=CONTENT_FORM,
            use_ajax=True,
            data={
                "ctl00$ContentPlaceHolder1$loginform$txtUserName": self.username,
                "txtPassword": self.password,
                VIEWSTATE_FIELD: fields[VIEWSTATE_FIELD],
                VIEWSTATEGENERATOR_FIELD: fields[VIEWSTATEGENERATOR_FIELD],
                EVENTVALIDATION_FIELD: fields[EVENTVALIDATION_FIELD],
                PREVIOUSPAGE_FIELD: fields[PREVIOUSPAGE_FIELD],
                "__EVENTTARGET": "",
                "__EVENTARGUMENT": "",
                "__VIEWSTATEENCRYPTED": "",
                "IsFromNewSite": "1",
            },
        )
        url_str = str(resp.url)
        if "m=login_fail" in url_str:
            raise RuntimeError("Login failed, bad username or password.")
        if "m=LockedOut" in url_str:
            raise RuntimeError("Account is locked out.")

        await self._load_identity()
        return await self._check_mfa()

    async def _load_identity(self) -> None:
        resp = await self._get(f"{API_URL_BASE}identities")
        body = await resp.json()
        data = body.get("data")
        if isinstance(data, list) and data:
            self.identity_id = data[0]["id"]
        elif isinstance(data, dict):
            self.identity_id = data["id"]
        else:
            raise RuntimeError("No identity data returned")

    async def _check_mfa(self) -> AuthResult:
        if not self.identity_id:
            raise RuntimeError("Identity not loaded")

        resp = await self._get(f"{API_URL_BASE}{TWO_FACTOR_PATH}/{self.identity_id}")
        body = await resp.json()
        attrs = body.get("data", {}).get("attributes", {})

        enabled_mask: int = attrs.get("enabledTwoFactorTypes", 0) or 0
        device_trusted: bool = attrs.get("isCurrentDeviceTrusted", False)

        if enabled_mask == 0 or device_trusted:
            return AuthResult.SUCCESS

        methods = [m for m in OtpType if m.value and (enabled_mask & m.value)]
        chosen: OtpType | None = None
        for preferred in (OtpType.sms, OtpType.email, OtpType.app):
            if preferred in methods:
                chosen = preferred
                break
        if not chosen:
            raise RuntimeError("No supported MFA method available")

        if chosen in (OtpType.sms, OtpType.email):
            action = (
                "sendTwoFactorAuthenticationCodeViaSms"
                if chosen == OtpType.sms
                else "sendTwoFactorAuthenticationCodeViaEmail"
            )
            await self._post(
                f"{API_URL_BASE}{TWO_FACTOR_PATH}/{self.identity_id}/{action}",
                accept=ACCEPT_JSON,
            )

        self._pending_mfa_type = chosen
        return AuthResult.MFA_REQUIRED

    async def submit_mfa_code(self, code: str) -> None:
        """Submit an MFA code and trust the current device."""
        if self._pending_mfa_type is None:
            raise RuntimeError("No MFA attempt pending")

        await self._post(
            f"{API_URL_BASE}{TWO_FACTOR_PATH}/{self.identity_id}/verifyTwoFactorCode",
            accept=ACCEPT_JSON,
            json_body={"code": code, "typeOf2FA": self._pending_mfa_type.value},
        )
        await self._post(
            f"{API_URL_BASE}{TWO_FACTOR_PATH}/{self.identity_id}/trustTwoFactorDevice",
            accept=ACCEPT_JSON,
            json_body={"deviceName": "Home Assistant Alarm.com Integration"},
        )
        self._pending_mfa_type = None

    async def close(self) -> None:
        if not self.session.closed:
            await self.session.close()

    async def ensure_logged_in(self) -> None:
        """Ensure camera session is authenticated."""
        result = await self.login()
        if result != AuthResult.SUCCESS:
            raise RuntimeError("Camera session requires MFA interaction")

    async def get_camera_list(self) -> list[dict[str, Any]]:
        """Return a list of camera summary dicts."""
        resp = await self._get(f"{API_URL_BASE}video/devices/cameras")
        body = await resp.json()
        cameras: list[dict[str, Any]] = []
        data = body.get("data", [])
        if isinstance(data, dict):
            data = [data]
        for cam in data:
            attrs = cam.get("attributes", {})
            summary: dict[str, Any] = {"id": cam.get("id")}
            summary.update(attrs)
            cameras.append(summary)
        return cameras

    async def get_stream_info(self, camera_id: str) -> dict[str, Any] | None:
        """Fetch the full live WebRTC config for a camera."""
        try:
            resp = await self._get(
                f"{API_URL_BASE}video/videoSources/liveVideoHighestResSources/{camera_id}",
            )
            body = await resp.json()
            top_attrs = body.get("data", {}).get("attributes", {})
            ice_servers_str = top_attrs.get("iceServers")
            ice_servers = json.loads(ice_servers_str) if ice_servers_str else []

            included = body.get("included", [])
            for inc in included:
                if inc.get("type") == "video/videoSources/endToEndWebrtcConnectionInfo":
                    config = inc.get("attributes", {})
                    config["iceServers"] = ice_servers
                    return config
            return None
        except aiohttp.ClientResponseError:
            return None

    async def get_snapshot(self, camera_id: str) -> bytes | None:
        """Best-effort snapshot retrieval.

        Alarm.com's snapshot endpoints are inconsistent across camera models. Try a
        small set of known paths and return the first image response.
        """
        candidate_urls = [
            f"{API_URL_BASE}video/snapshots/{camera_id}",
            f"{API_URL_BASE}video/snapshot/{camera_id}",
            f"{API_URL_BASE}video/devices/cameras/{camera_id}/snapshot",
        ]
        for url in candidate_urls:
            try:
                resp = await self.session.get(
                    url,
                    headers=_build_headers({"Accept": "image/*,*/*"}, self.ajax_key),
                    cookies=self._extra_cookies(),
                    allow_redirects=True,
                )
                self._extract_cookies(resp)
                if resp.status == 200 and resp.content_type.startswith("image/"):
                    return await resp.read()
            except aiohttp.ClientError:
                continue
        return None
