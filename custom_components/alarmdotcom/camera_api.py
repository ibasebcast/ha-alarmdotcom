"""Alarm.com camera API — WebRTC session manager."""

from __future__ import annotations

import json
import logging
from enum import Enum
from typing import TYPE_CHECKING

import aiohttp
from bs4 import BeautifulSoup

if TYPE_CHECKING:
    from pyalarmdotcomajax import AlarmBridge

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

URL_BASE     = "https://www.alarm.com/"
API_URL_BASE = URL_BASE + "web/api/"

MFA_COOKIE_KEY = "twoFactorAuthenticationId"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/123.0.0.0 Safari/537.36"
)
REFERER = "https://www.alarm.com/web/system/home"

VIEWSTATE_FIELD          = "__VIEWSTATE"
VIEWSTATEGENERATOR_FIELD = "__VIEWSTATEGENERATOR"
EVENTVALIDATION_FIELD    = "__EVENTVALIDATION"
PREVIOUSPAGE_FIELD       = "__PREVIOUSPAGE"

TWO_FACTOR_PATH = "engines/twoFactorAuthentication/twoFactorAuthentications"

_LOGGER = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class OtpType(Enum):
    """MFA types supported by Alarm.com."""
    disabled = 0
    app      = 1
    sms      = 2
    email    = 4


class AuthResult(Enum):
    """Result of an authentication attempt."""
    SUCCESS      = "success"
    MFA_REQUIRED = "mfa_required"
    ERROR        = "error"


# ---------------------------------------------------------------------------
# Header helpers
# ---------------------------------------------------------------------------

ACCEPT_HTML    = {"Accept": "text/html,application/xhtml+xml,application/xml"}
ACCEPT_JSON    = {"Accept": "application/json", "charset": "utf-8"}
ACCEPT_JSONAPI = {"Accept": "application/vnd.api+json", "charset": "utf-8"}
CONTENT_FORM   = {"Content-Type": "application/x-www-form-urlencoded", "charset": "utf-8"}


def _build_headers(
    accept: dict[str, str] | None = None,
    ajax_key: str | None = None,
) -> dict[str, str]:
    h: dict[str, str] = {
        "User-Agent": USER_AGENT,
        "Referer":    REFERER,
        "Connection": "keep-alive",
    }
    if accept:
        h.update(accept)
    if ajax_key:
        h["Ajaxrequestuniquekey"] = ajax_key
    return h


# ---------------------------------------------------------------------------
# AlarmCameraSession
# ---------------------------------------------------------------------------

class AlarmCameraSession:
    """Manages an authenticated Alarm.com HTTP session for camera/WebRTC access.

    Preferred construction: ``AlarmCameraSession.from_alarm_bridge(bridge)``
    which reuses the already-authenticated session owned by pyalarmdotcomajax,
    avoiding a second login entirely.

    Fall-back construction: ``AlarmCameraSession(username, password, ...)``
    performs its own independent login (scraper-based).
    """

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def __init__(
        self,
        username: str,
        password: str | None = None,
        cookie_jar: aiohttp.CookieJar | None = None,
        session: aiohttp.ClientSession | None = None,
        ajax_key: str | None = None,
        mfa_cookie: str | None = None,
        identity_id: str | None = None,
        *,
        _owns_session: bool = True,
    ) -> None:
        self.username    = username
        self.password    = password
        self.ajax_key    = ajax_key
        self.mfa_cookie  = mfa_cookie
        self.identity_id = identity_id
        self._owns_session = _owns_session

        self.cookie_jar = cookie_jar or aiohttp.CookieJar(unsafe=True)
        self.session    = session or aiohttp.ClientSession(cookie_jar=self.cookie_jar)

    @classmethod
    def from_alarm_bridge(cls, bridge: AlarmBridge, username: str, password: str, mfa_cookie: str | None = None) -> AlarmCameraSession:
        """Create a camera session that reuses the pyalarmdotcomajax HTTP session.

        This avoids a second login.  We walk a small set of known internal
        attribute paths that different versions of the library have used.
        If none are found we fall back to creating a fresh session that will
        do its own login.
        """
        # Candidate paths for the internal aiohttp.ClientSession across
        # pyalarmdotcomajax versions.
        _session_candidates = [
            lambda b: b._session,
            lambda b: b.auth_controller._session,
            lambda b: b._http_session,
            lambda b: b.auth_controller._http_session,
            lambda b: b._client,
        ]

        # Candidate paths for the AJAX key (afg cookie value)
        _ajax_key_candidates = [
            lambda b: b._ajax_key,
            lambda b: b.auth_controller._ajax_key,
            lambda b: b._afg,
            lambda b: b.auth_controller._afg,
        ]

        extracted_session: aiohttp.ClientSession | None = None
        extracted_ajax_key: str | None = None

        for fn in _session_candidates:
            try:
                val = fn(bridge)
                if isinstance(val, aiohttp.ClientSession) and not val.closed:
                    extracted_session = val
                    _LOGGER.debug("Camera session: reusing pyalarmdotcomajax internal session.")
                    break
            except AttributeError:
                continue

        for fn in _ajax_key_candidates:
            try:
                val = fn(bridge)
                if isinstance(val, str) and val:
                    extracted_ajax_key = val
                    _LOGGER.debug("Camera session: reusing pyalarmdotcomajax ajax key.")
                    break
            except AttributeError:
                continue

        if extracted_session is not None:
            # Reuse the bridge's session — do NOT close it on our behalf
            return cls(
                username=username,
                password=password,
                session=extracted_session,
                ajax_key=extracted_ajax_key,
                mfa_cookie=mfa_cookie,
                _owns_session=False,  # bridge owns it
            )

        # Fallback: independent session — will perform its own login
        _LOGGER.warning(
            "Camera session: could not extract session from pyalarmdotcomajax "
            "(library internals may have changed). Falling back to independent login."
        )
        return cls(username=username, password=password, mfa_cookie=mfa_cookie)

    # ------------------------------------------------------------------
    # Session persistence helpers
    # ------------------------------------------------------------------

    @property
    def session_data(self) -> dict:
        """Return session state dict for persistence."""
        return {
            "ajax_key":    self.ajax_key,
            "mfa_cookie":  self.mfa_cookie,
            "identity_id": self.identity_id,
        }

    # ------------------------------------------------------------------
    # Low-level request helpers
    # ------------------------------------------------------------------

    def _extra_cookies(self) -> dict[str, str]:
        """Inject MFA cookie explicitly (not always present in jar)."""
        return {MFA_COOKIE_KEY: self.mfa_cookie} if self.mfa_cookie else {}

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
        kwargs: dict = dict(
            headers=_build_headers(accept or ACCEPT_JSONAPI, self.ajax_key if use_ajax else None),
            cookies=self._extra_cookies(),
            allow_redirects=True,
        )
        if data      is not None: kwargs["data"] = data
        if json_body is not None: kwargs["json"] = json_body
        resp = await self.session.post(url, **kwargs)
        self._extract_cookies(resp)
        resp.raise_for_status()
        return resp

    # ------------------------------------------------------------------
    # Login (only used when session sharing failed)
    # ------------------------------------------------------------------

    async def login(self) -> AuthResult:
        """Perform full scraper login.  Called only when session could not
        be shared from pyalarmdotcomajax."""
        if not self.password:
            raise ValueError("Password required for independent login")

        _LOGGER.debug("[camera_api] Step 1: Loading login page...")
        resp = await self._get(f"{URL_BASE}login", accept=ACCEPT_HTML, use_ajax=False)
        html = await resp.text()
        soup = BeautifulSoup(html, "html.parser")

        fields: dict[str, str] = {}
        for fid in (VIEWSTATE_FIELD, VIEWSTATEGENERATOR_FIELD, EVENTVALIDATION_FIELD, PREVIOUSPAGE_FIELD):
            el = soup.select_one(f"#{fid}")
            if el is None:
                raise RuntimeError(f"Could not find #{fid} in login page HTML")
            fields[fid] = str(el.attrs.get("value", ""))

        _LOGGER.debug("[camera_api] Step 2: Submitting credentials...")
        resp = await self._post(
            f"{URL_BASE}web/Default.aspx",
            accept=CONTENT_FORM,
            use_ajax=True,
            data={
                "ctl00$ContentPlaceHolder1$loginform$txtUserName": self.username,
                "txtPassword": self.password,
                VIEWSTATE_FIELD:          fields[VIEWSTATE_FIELD],
                VIEWSTATEGENERATOR_FIELD: fields[VIEWSTATEGENERATOR_FIELD],
                EVENTVALIDATION_FIELD:    fields[EVENTVALIDATION_FIELD],
                PREVIOUSPAGE_FIELD:       fields[PREVIOUSPAGE_FIELD],
                "__EVENTTARGET":          "",
                "__EVENTARGUMENT":        "",
                "__VIEWSTATEENCRYPTED":   "",
                "IsFromNewSite":          "1",
            },
        )
        url_str = str(resp.url)
        if "m=login_fail" in url_str:
            raise RuntimeError("Login failed — bad username or password.")
        if "m=LockedOut" in url_str:
            raise RuntimeError("Account is locked out.")

        await self._load_identity()
        return await self._check_mfa()

    async def _load_identity(self) -> None:
        _LOGGER.debug("[camera_api] Loading user identity...")
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
        """Check MFA.  If MFA is required but we have no interactive prompt,
        log a warning and return MFA_REQUIRED so the caller can handle it."""
        _LOGGER.debug("[camera_api] Checking MFA requirements...")
        resp = await self._get(f"{API_URL_BASE}{TWO_FACTOR_PATH}/{self.identity_id}")
        body = await resp.json()
        attrs = body.get("data", {}).get("attributes", {})

        enabled_mask: int = attrs.get("enabledTwoFactorTypes", 0) or 0
        device_trusted: bool = attrs.get("isCurrentDeviceTrusted", False)

        if enabled_mask == 0 or device_trusted:
            _LOGGER.info("[camera_api] MFA not required (trusted device).")
            return AuthResult.SUCCESS

        # MFA required on independent session — the main integration's MFA
        # flow will have trusted the device, so this should rarely trigger.
        # If it does, log clearly rather than hanging silently.
        _LOGGER.warning(
            "[camera_api] MFA required on camera session but no interactive "
            "prompt is available. This should not happen if the main integration "
            "has already trusted this device. Camera may be unavailable until "
            "the device is trusted via the main integration's re-auth flow."
        )
        self._pending_mfa_type = None
        return AuthResult.MFA_REQUIRED

    # ------------------------------------------------------------------
    # Camera discovery & stream
    # ------------------------------------------------------------------

    async def get_camera_list(self) -> list[dict]:
        """Return list of camera summary dicts."""
        resp = await self._get(f"{API_URL_BASE}video/devices/cameras")
        body = await resp.json()
        data = body.get("data", [])
        if isinstance(data, dict):
            data = [data]
        cameras: list[dict] = []
        for cam in data:
            attrs   = cam.get("attributes", {})
            summary = {"id": cam.get("id")}
            summary.update(attrs)
            cameras.append(summary)
        return cameras

    async def get_stream_info(self, camera_id: str) -> dict | None:
        """Fetch WebRTC config (ICE servers + signalling tokens) for a camera."""
        try:
            resp = await self._get(
                f"{API_URL_BASE}video/videoSources/liveVideoHighestResSources/{camera_id}"
            )
            body = await resp.json()

            top_attrs     = body.get("data", {}).get("attributes", {})
            ice_servers_s = top_attrs.get("iceServers")
            ice_servers   = json.loads(ice_servers_s) if ice_servers_s else []

            for inc in body.get("included", []):
                if inc.get("type") == "video/videoSources/endToEndWebrtcConnectionInfo":
                    config = inc.get("attributes", {})
                    config["iceServers"] = ice_servers
                    return config

            return None
        except aiohttp.ClientResponseError:
            return None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def close(self) -> None:
        """Close the HTTP session — only if we own it."""
        if self._owns_session and self.session and not self.session.closed:
            await self.session.close()
