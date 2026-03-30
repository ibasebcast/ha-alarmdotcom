"""Alarm.com camera API, WebRTC session manager."""

from __future__ import annotations

import json
import logging
from enum import Enum
from typing import TYPE_CHECKING

import aiohttp
from bs4 import BeautifulSoup

if TYPE_CHECKING:
    from pyalarmdotcomajax import AlarmBridge

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
    """Manages an authenticated Alarm.com HTTP session for camera/WebRTC access."""

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
        self.username = username
        self.password = password
        self.ajax_key = ajax_key
        self.mfa_cookie = mfa_cookie
        self.identity_id = identity_id
        self._owns_session = _owns_session

        self.cookie_jar = cookie_jar or aiohttp.CookieJar(unsafe=True)
        self.session = session or aiohttp.ClientSession(cookie_jar=self.cookie_jar)

    @classmethod
    def from_alarm_bridge(
        cls,
        bridge: AlarmBridge,
        username: str,
        password: str,
        mfa_cookie: str | None = None,
    ) -> AlarmCameraSession:
        """Create a camera session that reuses the pyalarmdotcomajax HTTP session."""

        session_candidates = [
            lambda b: getattr(b, "_websession", None),
            lambda b: getattr(b, "_session", None),
            lambda b: getattr(b, "_http_session", None),
            lambda b: getattr(getattr(b, "_auth_controller", None), "_session", None),
            lambda b: getattr(getattr(b, "_auth_controller", None), "_http_session", None),
            lambda b: getattr(b, "_client", None),
        ]

        ajax_key_candidates = [
            lambda b: getattr(b, "ajax_key", None),
            lambda b: getattr(b, "_ajax_key", None),
            lambda b: getattr(b, "_afg", None),
            lambda b: getattr(getattr(b, "_auth_controller", None), "_ajax_key", None),
            lambda b: getattr(getattr(b, "_auth_controller", None), "_afg", None),
        ]

        mfa_candidates = [
            lambda b: getattr(getattr(b, "_auth_controller", None), "mfa_cookie", None),
        ]

        extracted_session: aiohttp.ClientSession | None = None
        extracted_ajax_key: str | None = None
        extracted_mfa_cookie: str | None = None

        for fn in session_candidates:
            try:
                val = fn(bridge)
                if isinstance(val, aiohttp.ClientSession) and not val.closed:
                    extracted_session = val
                    _LOGGER.debug(
                        "Camera session: reusing pyalarmdotcomajax internal session."
                    )
                    break
            except Exception:
                continue

        for fn in ajax_key_candidates:
            try:
                val = fn(bridge)
                if isinstance(val, str) and val:
                    extracted_ajax_key = val
                    _LOGGER.debug("Camera session: reusing pyalarmdotcomajax ajax key.")
                    break
            except Exception:
                continue

        for fn in mfa_candidates:
            try:
                val = fn(bridge)
                if isinstance(val, str) and val:
                    extracted_mfa_cookie = val
                    break
            except Exception:
                continue

        if extracted_session is not None:
            return cls(
                username=username,
                password=password,
                session=extracted_session,
                ajax_key=extracted_ajax_key,
                mfa_cookie=extracted_mfa_cookie or mfa_cookie,
                _owns_session=False,
            )

        _LOGGER.warning(
            "Camera session: could not extract session from pyalarmdotcomajax "
            "(library internals may have changed). Falling back to independent login."
        )
        return cls(username=username, password=password, mfa_cookie=mfa_cookie)

    @property
    def session_data(self) -> dict:
        """Return session state dict for persistence."""
        return {
            "ajax_key": self.ajax_key,
            "mfa_cookie": self.mfa_cookie,
            "identity_id": self.identity_id,
        }

    def _extra_cookies(self) -> dict[str, str]:
        """Inject MFA cookie explicitly when needed."""
        return {MFA_COOKIE_KEY: self.mfa_cookie} if self.mfa_cookie else {}

    def _extract_cookies(self, resp: aiohttp.ClientResponse) -> None:
        afg = resp.cookies.get("afg")
        if afg:
            self.ajax_key = afg.value

        mfa = resp.cookies.get(MFA_COOKIE_KEY)
        if mfa and mfa.value != self.mfa_cookie:
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
        kwargs: dict = {
            "headers": _build_headers(
                accept or ACCEPT_JSONAPI,
                self.ajax_key if use_ajax else None,
            ),
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
        """Perform full scraper login."""
        if not self.password:
            raise ValueError("Password required for independent login")

        _LOGGER.debug("Loading login page...")
        resp = await self._get(f"{URL_BASE}login", accept=ACCEPT_HTML, use_ajax=False)
        html = await resp.text()
        soup = BeautifulSoup(html, "html.parser")

        fields: dict[str, str] = {}
        for fid in (
            VIEWSTATE_FIELD,
            VIEWSTATEGENERATOR_FIELD,
            EVENTVALIDATION_FIELD,
            PREVIOUSPAGE_FIELD,
        ):
            el = soup.select_one(f"#{fid}")
            if el is None:
                raise RuntimeError(f"Could not find #{fid} in login page HTML")
            fields[fid] = str(el.attrs.get("value", ""))

        _LOGGER.debug("Submitting credentials...")
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
        _LOGGER.debug("Loading user identity...")
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
        """Check MFA requirement."""
        _LOGGER.debug("Checking MFA requirements...")
        resp = await self._get(f"{API_URL_BASE}{TWO_FACTOR_PATH}/{self.identity_id}")
        body = await resp.json()
        attrs = body.get("data", {}).get("attributes", {})

        enabled_mask: int = attrs.get("enabledTwoFactorTypes", 0) or 0
        device_trusted: bool = attrs.get("isCurrentDeviceTrusted", False)

        if enabled_mask == 0 or device_trusted:
            _LOGGER.info("MFA not required (trusted device).")
            return AuthResult.SUCCESS

        _LOGGER.warning(
            "MFA required on camera session but no interactive "
            "prompt is available. This should not happen if the main integration "
            "has already trusted this device. Camera may be unavailable until "
            "the device is trusted via the main integration's re-auth flow."
        )
        self._pending_mfa_type = None
        return AuthResult.MFA_REQUIRED

    async def get_camera_list(self) -> list[dict]:
        """Return list of camera summary dicts."""
        resp = await self._get(f"{API_URL_BASE}video/devices/cameras")
        body = await resp.json()
        data = body.get("data", [])

        if isinstance(data, dict):
            data = [data]

        cameras: list[dict] = []
        for cam in data:
            attrs = cam.get("attributes", {})
            summary = {"id": cam.get("id")}
            summary.update(attrs)
            cameras.append(summary)

        return cameras

    async def get_stream_info(self, camera_id: str) -> dict | None:
        """Fetch WebRTC config for a camera.

        Important: do not swallow ClientResponseError here.
        camera.py needs 401/403 to bubble up so it can retry auth.
        """
        resp = await self._get(
            f"{API_URL_BASE}video/videoSources/liveVideoHighestResSources/{camera_id}"
        )
        body = await resp.json()

        _LOGGER.debug(
            "get_stream_info raw response for camera %s: %s",
            camera_id,
            body,
        )

        top_attrs = body.get("data", {}).get("attributes", {})
        ice_servers_s = top_attrs.get("iceServers")

        try:
            ice_servers = json.loads(ice_servers_s) if ice_servers_s else []
        except Exception as err:
            _LOGGER.warning(
                "Failed to parse iceServers for camera %s: %s",
                camera_id,
                err,
            )
            ice_servers = []

        included = body.get("included", [])

        for inc in included:
            if inc.get("type") == "video/videoSources/endToEndWebrtcConnectionInfo":
                config = dict(inc.get("attributes", {}))
                config["iceServers"] = ice_servers
                config["streamType"] = "endToEnd"
                _LOGGER.debug(
                    "Found end-to-end WebRTC config for camera %s",
                    camera_id,
                )
                return config

        if top_attrs.get("janusGatewayUrl") and top_attrs.get("janusToken"):
            # Find the HD stream mountpoint ID from the quality message included items.
            # Alarm.com includes webrtcStreamQualityMessage entries with a streamID field;
            # the HD entry (id suffix "-Hd") carries the Janus mountpoint ID.
            janus_stream_id: int | None = None
            camera_id_hd = f"{camera_id}-Hd"
            for inc in included:
                if (
                    inc.get("type") == "video/videoSources/webrtcStreamQualityMessage"
                    and inc.get("id") == camera_id_hd
                ):
                    janus_stream_id = inc.get("attributes", {}).get("streamID")
                    break
            # Fall back to SD if HD not found
            if janus_stream_id is None:
                camera_id_sd = f"{camera_id}-Sd"
                for inc in included:
                    if (
                        inc.get("type") == "video/videoSources/webrtcStreamQualityMessage"
                        and inc.get("id") == camera_id_sd
                    ):
                        janus_stream_id = inc.get("attributes", {}).get("streamID")
                        break

            # Last resort: parse the numeric suffix from the camera ID itself.
            # e.g. "110353471-2048" → 2048. This is used for cameras that don't
            # include quality message entries in their API response.
            if janus_stream_id is None:
                try:
                    janus_stream_id = int(camera_id.rsplit("-", 1)[-1])
                    _LOGGER.debug(
                        "Derived Janus stream ID %s from camera ID suffix for camera %s",
                        janus_stream_id,
                        camera_id,
                    )
                except (ValueError, IndexError):
                    pass

            config = {
                "streamType": "janus",
                "janusGatewayUrl": top_attrs["janusGatewayUrl"],
                "janusToken": top_attrs["janusToken"],
                "janusStreamId": janus_stream_id,
                "proxyUrl": top_attrs.get("proxyUrl"),
                "iceServers": ice_servers,
            }
            _LOGGER.debug(
                "Found Janus proxy WebRTC config for camera %s (streamId=%s)",
                camera_id,
                janus_stream_id,
            )
            return config

        _LOGGER.warning(
            "No WebRTC config found for camera %s. "
            "included types: %s. Top-level keys: %s",
            camera_id,
            [inc.get("type") for inc in included],
            list(top_attrs.keys()),
        )
        return None

    async def close(self) -> None:
        """Close the HTTP session only if we own it."""
        if self._owns_session and self.session and not self.session.closed:
            await self.session.close()