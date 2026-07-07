"""pyalarmdotcomajax - A Python library for interacting with Alarm.com's API."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from collections.abc import AsyncIterator, Callable
from datetime import datetime
from types import TracebackType
from typing import TYPE_CHECKING, Any, Literal, TypeVar, overload

import aiohttp
import humps
from mashumaro.exceptions import MissingField
from rich.console import Group

from _pyalarmdotcomajax._version import __version__

from _pyalarmdotcomajax.const import (
    API_URL_BASE,
    DEBUG_REQUEST_DUMP_MAX_LEN,
    REQUEST_RETRY_LIMIT,
    SUBMIT_RETRY_LIMIT,
    URL_BASE,
    ResponseTypes,
)
from _pyalarmdotcomajax.controllers import (
    AdcControllerT,
    AdcSuccessDocumentMulti,
    AdcSuccessDocumentSingle,
)
from _pyalarmdotcomajax.controllers.auth import AuthenticationController
from _pyalarmdotcomajax.controllers.base import BaseController
from _pyalarmdotcomajax.controllers.cameras import CameraController
from _pyalarmdotcomajax.controllers.device_catalogs import DeviceCatalogController
from _pyalarmdotcomajax.controllers.garage_doors import GarageDoorController
from _pyalarmdotcomajax.controllers.gates import GateController
from _pyalarmdotcomajax.controllers.image_sensors import (
    ImageSensorController,
    ImageSensorImageController,
)
from _pyalarmdotcomajax.controllers.lights import LightController
from _pyalarmdotcomajax.controllers.locks import LockController
from _pyalarmdotcomajax.controllers.partitions import PartitionController
from _pyalarmdotcomajax.controllers.sensors import SensorController
from _pyalarmdotcomajax.controllers.systems import SystemController
from _pyalarmdotcomajax.controllers.thermostats import ThermostatController
from _pyalarmdotcomajax.controllers.trouble_conditions import TroubleConditionController
from _pyalarmdotcomajax.controllers.users import (
    AvailableSystemsController,
)
from _pyalarmdotcomajax.controllers.water_sensors import WaterSensorController
from _pyalarmdotcomajax.controllers.water_valve import WaterValveController
from _pyalarmdotcomajax.events import (
    EventBroker,
    EventBrokerCallbackT,
    EventBrokerMessage,
    EventBrokerTopic,
    ResourceEventMessage,
)
from _pyalarmdotcomajax.exceptions import (
    AlarmdotcomException,
    AuthenticationException,
    AuthenticationFailed,
    MustConfigureMfa,
    NotAuthorized,
    NotInitialized,
    OtpRequired,
    ServiceUnavailable,
    SessionExpired,
    UnexpectedResponse,
    UnknownDevice,
    UnsupportedOperation,
)
from _pyalarmdotcomajax.models import (
    AdcManagedDeviceT,
    AdcMiniSuccessResponse,
    AdcResourceT,
    base,
    camera,
    garage_door,
    gate,
    image_sensor,
    light,
    lock,
    partition,
    sensor,
    system,
    thermostat,
    trouble_condition,
    user,
    water_sensor,
    water_valve,
)
from _pyalarmdotcomajax.models.auth import OtpType
from _pyalarmdotcomajax.models.base import (
    AdcDeviceResource,
    AdcResource,
    BaseManagedDeviceAttributes,
    ResourceType,
)
from _pyalarmdotcomajax.models.jsonapi import (
    FailureDocument,
    JsonApiBaseElement,
    MetaDocument,
    SuccessDocument,
)
from _pyalarmdotcomajax.websocket.client import (
    ConnectionEvent,
    WebSocketClient,
    WebSocketState,
)

if TYPE_CHECKING:
    from _pyalarmdotcomajax.models.system import System

__all__: tuple[str, ...] = (  # noqa: RUF022
    # exceptions
    "AlarmdotcomException",
    "UnsupportedOperation",
    "UnknownDevice",
    "AuthenticationFailed",
    "AuthenticationException",
    "OtpRequired",
    "MustConfigureMfa",
    "SessionExpired",
    "ServiceUnavailable",
    "NotAuthorized",
    "NotInitialized",
    "UnexpectedResponse",
    # models.auth
    "OtpType",
    # websocket
    "WebSocketState",
    "ConnectionEvent",
    # events
    "EventBrokerTopic",
    "EventBrokerMessage",
    "EventBrokerCallbackT",
    "ResourceEventMessage",
    # models
    "AdcResourceT",
    "AdcManagedDeviceT",
    "base",
    "camera",
    "garage_door",
    "gate",
    "image_sensor",
    "light",
    "lock",
    "partition",
    "sensor",
    "system",
    "thermostat",
    "trouble_condition",
    "user",
    "water_sensor",
    "water_valve",
    # controllers
    "AdcControllerT",
    "ResourceEventMessage",
)
T = TypeVar("T", bound=JsonApiBaseElement)

log = logging.getLogger(__name__)

FORK_NAME = "ibasebcast"
FORK_REPO = "https://github.com/ibasebcast/pyalarmdotcomajax"

MFA_COOKIE_KEY = "twoFactorAuthenticationId"


class AlarmBridge:
    """Alarm.com bridge."""

    def __init__(
        self,
        username: str | None = None,
        password: str | None = None,
        mfa_token: str | None = None,
    ) -> None:
        """Initialize alarm bridge."""

        # We allow username and password to be set after initialization so that we can use an instantiated
        # (but not initialized) AlarmBridge to populate the adc cli command list.

        self._initialized = False

        # Event Broker
        self.events = EventBroker()

        # Session
        self._websession: aiohttp.ClientSession | None = None
        self.ajax_key: str | None = None

        # Session Controllers
        self._auth_controller = AuthenticationController(
            self, username, password, mfa_token
        )
        self._ws_controller = WebSocketClient(self)

        # Meta Resource Controllers
        self._available_device_catalogs = AvailableSystemsController(self)
        self._systems = SystemController(self)
        self._trouble_conditions = TroubleConditionController(self)

        # Device Resource Controllers
        self._device_catalogs = DeviceCatalogController(self)
        self._cameras = CameraController(self, self._device_catalogs)
        self._garage_doors = GarageDoorController(self, self._device_catalogs)
        self._lights = LightController(self, self._device_catalogs)
        self._gates = GateController(self, self._device_catalogs)
        self._locks = LockController(self, self._device_catalogs)
        self._partitions = PartitionController(self, self._device_catalogs)
        self._sensors = SensorController(self, self._device_catalogs)
        self._thermostats = ThermostatController(self, self._device_catalogs)
        self._water_sensors = WaterSensorController(self, self._device_catalogs)
        self._water_valves = WaterValveController(self, self._device_catalogs)

        self._image_sensors = ImageSensorController(self)
        self._image_sensor_images = ImageSensorImageController(self)
        log.debug(
            "IBASEBCAST pyalarmdotcomajax fork loaded, version=%s, repo=%s",
            __version__,
            FORK_REPO,
        )

    async def initialize(self) -> None:
        """Initialize bridge connection, or finish initialization after OTP has been submitted."""

        # TODO: REFRESH IMAGE SENSORS / PROFILE / ETC ON SCHEDULE (DO IN INTEGRATION)
        # TODO: SKYBELL HD

        if self._initialized:
            return

        if not await self.is_logged_in():
            await self.login()

        await self.fetch_full_state()

        self._initialized = True

    async def is_logged_in(self, *, throw: bool = False) -> bool:
        """Check if we are still logged in. Also functions as keep alive signal."""

        try:
            url = f"{URL_BASE[:-1]}{self.auth_controller.keep_alive_url}?"
            f"timestamp={round(datetime.now().timestamp())}"
        except IndexError as err:
            # User has yet to log in.
            if throw:
                raise NotInitialized from err

            return False

        text_rsp = ""

        try:
            async with self.create_request(
                "post",
                url,
                accept_types=ResponseTypes.JSON,
                use_ajax_key=True,
                raise_for_status=True,
                json={},
            ) as rsp:
                text_rsp = await rsp.text()

        except aiohttp.ClientResponseError as err:
            if err.status == 403:
                log.debug("Session expired.")

                if throw:
                    raise SessionExpired from err

                return False

            raise UnexpectedResponse(
                f"Failed to send keep alive signal. Response: {text_rsp}"
            ) from err

        return True

    async def login(self) -> None:
        """Login to alarm.com."""

        return await self._auth_controller.login()

    async def fetch_full_state(self) -> None:
        """Fetch full state from alarm.com."""

        # 1. Initialize system and device catalog controllers first
        await self._available_device_catalogs.initialize()
        if not self._available_device_catalogs.active_system_id:
            raise AuthenticationFailed("No active system found.")
        await self._systems.initialize()
        await self._device_catalogs.initialize(
            [self._available_device_catalogs.active_system_id]
        )
        await self._partitions.initialize()
        if self._auth_controller.has_trouble_conditions_service:
            await self._trouble_conditions.initialize()

        # 2. Gather device IDs for each device controller type
        device_ids_by_type: dict[type, list[str]] = {}
        for controller in self.resource_controllers:
            if controller.is_device_controller:
                resource_type = controller.resource_type
                # Use the system controller's items for device discovery
                # Within each relationship entry in relationships, we're looking at type in each ResourceIdentifier in data.
                if resource_type and (
                    relationships := self._systems.items[0].api_resource.relationships
                ):
                    for relationship in relationships.values():
                        for resource_identifier in relationship.data_list:
                            if resource_identifier.type == resource_type:
                                device_ids_by_type.setdefault(
                                    type(controller), []
                                ).append(resource_identifier.id)

        log.debug("Discovered device IDs by type: %s", device_ids_by_type)

        # 3. Initialize device controllers with discovered device IDs (or empty list)
        init_tasks = []
        for controller in self.resource_controllers:
            if controller.is_device_controller:
                ids = device_ids_by_type.get(type(controller), [])
                # Most controllers have already been initialized as dependents of the device catalog controller.
                # We're counting on the initialize() method to check if the controller is already initialized.
                # This entire process is to ensure that we don't hit the image sensor endpoint if we don't have
                # any image sensors. Doing so causes a 423 error.
                init_tasks.append(controller.initialize(target_device_ids=ids))
        if init_tasks:
            await asyncio.gather(*init_tasks)

    async def refresh_all_resources(self) -> None:
        """Force a re-fetch and re-publish of state for every already-initialized resource controller.

        fetch_full_state() (and the controller.initialize() calls it makes) is a one-time
        setup path: each controller's initialize() returns immediately if it has already run
        once, so calling fetch_full_state() again - e.g. from a periodic safety-net poll meant
        to catch state missed by a dropped WebSocket event - is a silent no-op. It does not
        raise, log a warning, or refresh anything.

        This method instead calls each controller's _refresh() directly, the same mechanism
        already used to catch up state when the WebSocket reconnects (see
        BaseController._base_handle_event). Unlike initialize(), _refresh() has no one-time
        guard and safely re-fetches and re-publishes RESOURCE_UPDATED events every time it's
        called.
        """

        refresh_tasks = [
            controller._refresh()  # noqa: SLF001
            for controller in self.resource_controllers
            if controller.initialized
        ]

        if refresh_tasks:
            await asyncio.gather(*refresh_tasks, return_exceptions=True)


    async def start_event_monitoring(
        self, ws_status_callback: EventBrokerCallbackT | None = None
    ) -> None | Callable:
        """Start real-time event monitoring."""

        await self._ws_controller.initialize()

        if ws_status_callback:
            return self.events.subscribe(
                EventBrokerTopic.CONNECTION_EVENT, ws_status_callback
            )

        return None

    def subscribe(
        self,
        callback: EventBrokerCallbackT,
        ids: list[str] | str | None = None,
    ) -> Callable[[], None]:
        """
        Subscribe to status changes for all resource controllers.

        Returns:
            function to unsubscribe.

        """
        return self.events.subscribe(
            [
                EventBrokerTopic.RESOURCE_ADDED,
                EventBrokerTopic.RESOURCE_DELETED,
                EventBrokerTopic.RESOURCE_UPDATED,
                EventBrokerTopic.CONNECTION_EVENT,
            ],
            callback,
            ids,
        )

    ###################
    # GET CONTROLLERS #
    ###################

    @property
    def lights(self) -> LightController:
        """Get the lights controller."""

        return self._lights

    @property
    def cameras(self) -> CameraController:
        """Get the cameras controller."""
        return self._cameras

    @property
    def garage_doors(self) -> GarageDoorController:
        """Get the garage doors controller."""
        return self._garage_doors

    @property
    def gates(self) -> GateController:
        """Get the gates controller."""
        return self._gates

    @property
    def image_sensors(self) -> ImageSensorController:
        """Get the image sensors controller."""
        return self._image_sensors

    @property
    def image_sensor_images(self) -> ImageSensorImageController:
        """Get the image sensor images controller."""
        return self._image_sensor_images

    @property
    def locks(self) -> LockController:
        """Get the locks controller."""
        return self._locks

    @property
    def partitions(self) -> PartitionController:
        """Get the partitions controller."""
        return self._partitions

    @property
    def sensors(self) -> SensorController:
        """Get the sensors controller."""
        return self._sensors

    @property
    def systems(self) -> SystemController:
        """Get the system controller."""
        return self._systems

    @property
    def thermostats(self) -> ThermostatController:
        """Get the thermostats controller."""
        return self._thermostats

    @property
    def trouble_conditions(self) -> TroubleConditionController:
        """Get the trouble conditions controller."""
        return self._trouble_conditions

    @property
    def water_sensors(self) -> WaterSensorController:
        """Get the water sensors controller."""
        return self._water_sensors

    @property
    def water_valves(self) -> WaterValveController:
        """Get the water valves controller."""
        return self._water_valves

    @property
    def auth_controller(self) -> AuthenticationController:
        """Get the authentication controller."""
        return self._auth_controller

    @property
    def ws_controller(self) -> WebSocketClient:
        """Get the websocket controller."""
        return self._ws_controller

    @property
    def device_catalogs(self) -> DeviceCatalogController:
        """Get the device catalogs controller."""
        return self._device_catalogs

    @property
    def resource_controllers(self) -> list[BaseController]:
        """Get all resource controllers."""

        # Build and return list of resource controllers by searching self for all attributes that inherit from
        # BaseController
        return [
            controller
            for controller in self.__dict__.values()
            if isinstance(controller, BaseController)
        ]

    def get_controller(self, resource_id: str) -> BaseController:
        """Get the resource controller for a given resource."""

        for controller in self.resource_controllers:
            if resource_id in controller:
                return controller

        raise UnknownDevice(f"Couldn't find controller for: {resource_id}")

    ###################################
    ## PROPERTIES & RESOURCE FINDERS ##
    ###################################

    @property
    def initialized(self) -> bool:
        """Return whether bridge is initialized."""

        return self._initialized

    @property
    def active_system(self) -> System:
        """Get the active system."""

        if not self._available_device_catalogs.active_system_id:
            raise AuthenticationFailed("No active system found.")

        return self._systems[self._available_device_catalogs.active_system_id]

    @property
    def resources(self) -> dict[str, AdcResource]:
        """Get ADC resources across all controllers."""

        return {
            resource.id: resource
            for controller in self.resource_controllers
            for resource in controller.items
            if isinstance(resource, AdcResource)
        }

    @property
    def managed_devices(
        self,
    ) -> dict[str, AdcDeviceResource[BaseManagedDeviceAttributes]]:
        """Get ADC resources across all controllers."""

        return {
            resource.id: resource
            for controller in self.resource_controllers
            for resource in controller.items
            if isinstance(resource, AdcDeviceResource)
            and isinstance(resource.attributes, BaseManagedDeviceAttributes)
        }

    ##########################################
    # REQUEST MANAGEMENT / CONTEXT FUNCTIONS #
    ##########################################

    async def __aenter__(self) -> AlarmBridge:
        """Return Context manager."""

        await self.initialize()

        await self.start_event_monitoring()

        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Exit context manager."""

        await self.close()

    async def close(self) -> None:
        """Close connection and cleanup."""

        self._ws_controller.stop()

        if self._websession:
            await self._websession.close()
        log.info("Connection to alarm.com closed.")

    #
    # REQUEST FUNCTIONS
    #

    def build_request_headers(
        self,
        accept_types: ResponseTypes | None = ResponseTypes.JSONAPI,
        *,
        use_ajax_key: bool = True,
        **kwargs: Any,
    ) -> Any:
        """Get session and build headers for request."""

        if "headers" not in kwargs:
            kwargs["headers"] = {}

        kwargs["headers"].update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
                ),
                "Referrer": "https://www.alarm.com/web/system/home",
                "Connection": "keep-alive",
            }
        )

        if accept_types is not None:
            kwargs["headers"].update(accept_types.value)

        if use_ajax_key and self.ajax_key:
            kwargs["headers"].update({"Ajaxrequestuniquekey": self.ajax_key})

        return kwargs

    @contextlib.asynccontextmanager
    async def create_request(
        self,
        method: str,
        url: str,
        accept_types: ResponseTypes = ResponseTypes.JSONAPI,
        *,
        use_ajax_key: bool = True,
        **kwargs: Any,
    ) -> AsyncIterator[aiohttp.ClientResponse]:
        """
        Make a request to the Alarm.com API.

        Returns a generator with aiohttp ClientResponse.
        """

        if self._websession is None:
            log.debug("Creating new websession.")
            self._websession = aiohttp.ClientSession()

        if self._auth_controller.mfa_cookie:
            kwargs.setdefault("cookies", {}).update(
                {MFA_COOKIE_KEY: self._auth_controller.mfa_cookie}
            )

        kwargs = self.build_request_headers(
            accept_types=accept_types, use_ajax_key=use_ajax_key, **kwargs
        )

        async with self._websession.request(method, url, **kwargs) as resp:
            # Update anti-forgery cookie.

            # AFG cookie is not always used. This seems to depend on the specific Alarm.com vendor, so a missing
            # AFG key should not cause a failure.
            # Ref: https://www.alarm.com/web/system/assets/addon-tree-output/@adc/ajax/services/adc-ajax.js
            # When used, AFG is not always present in the response. Prior value should carry over until a new value
            # appears.

            if afg := resp.cookies.get("afg"):
                self.ajax_key = afg.value

            # Update MFA cookie.
            # We need to store the MFA cookie locally in order to reauthenticate after a session timeout without
            # having to reprompt for an OTP.
            #
            # Alarm.com sets the twoFactorAuthenticationId cookie on the verifyTwoFactorCode /
            # trustTwoFactorDevice responses, but it is not always present on the final
            # ClientResponse: aiohttp follows redirects by default, and resp.cookies only exposes
            # the Set-Cookie headers of the *last* response in the chain. The session cookie jar,
            # however, accumulates cookies from every hop, so fall back to it when the cookie is
            # not on this response. Without this, OTP verification silently fails to produce a
            # token and login is rejected with "Could not find MFA cookie".

            new_mfa_cookie: str | None = None
            if resp_mfa_cookie := resp.cookies.get(MFA_COOKIE_KEY):
                new_mfa_cookie = resp_mfa_cookie.value
            elif self._websession is not None:
                for jar_cookie in self._websession.cookie_jar:
                    if jar_cookie.key == MFA_COOKIE_KEY and jar_cookie.value:
                        new_mfa_cookie = jar_cookie.value
                        break

            if new_mfa_cookie and new_mfa_cookie != self._auth_controller.mfa_cookie:
                log.debug("Got new token from MFA cookie.")
                self._auth_controller.mfa_cookie = new_mfa_cookie

            # If DEBUG logging is enabled, log the request and response.
            if log.level < logging.DEBUG:
                try:
                    resp_dump = (
                        json.dumps(await resp.json()) if resp.content_length else ""
                    )
                except (json.JSONDecodeError, aiohttp.ContentTypeError):
                    if resp.content_type == "text/html":
                        resp_dump = "***OMITTING HTML OUTPUT***"
                    else:
                        resp_dump = await resp.text() if resp.content_length else ""

                log.debug(
                    "\n===========================Server Request (%s) / Response (%s)===========================\n"
                    "URL: %s\n"
                    "REQUEST HEADERS:\n%s\n"
                    "REQUEST BODY:\n%s\n"
                    "RESPONSE HEADERS:\n%s\n"
                    "RESPONSE BODY:\n%s\n"
                    "URL: %s\n"
                    "=================================================================================\n",
                    resp.request_info.method,
                    resp.status,
                    url,
                    json.dumps(dict(resp.request_info.headers)),
                    kwargs.get("data") or kwargs.get("json"),
                    json.dumps(dict(resp.headers)),
                    resp_dump[:DEBUG_REQUEST_DUMP_MAX_LEN]
                    + "..." * (len(resp_dump) > DEBUG_REQUEST_DUMP_MAX_LEN),
                    url,
                )

            yield resp

    @contextlib.asynccontextmanager
    async def ws_connect(
        self,
        url: str,
        **kwargs: Any,
    ) -> AsyncIterator[aiohttp.ClientWebSocketResponse]:
        """
        Establish a WebSocket connection with Alarm.com.

        Returns a generator with aiohttp ClientWebSocketResponse.
        """
        if self._websession is None:
            raise NotInitialized(
                "Cannot initiate WebSocket connection without an existing session."
            )

        # Don't generate/use GET/POST request headers. WebSocket connection uses token in place of cookies, etc.

        async with self._websession.ws_connect(url, **kwargs) as res:
            yield res

    @overload
    async def request(
        self,
        method: str,
        url: str,
        accept_types: ResponseTypes,
        success_response_class: type[T],
        **kwargs: Any,
    ) -> T: ...

    @overload
    async def request(
        self,
        method: str,
        url: str,
        accept_types: ResponseTypes,
        success_response_class: type[SuccessDocument] = SuccessDocument,
        **kwargs: Any,
    ) -> SuccessDocument: ...

    async def request(
        self,
        method: str,
        url: str,
        accept_types: ResponseTypes = ResponseTypes.JSONAPI,
        success_response_class: type[T] | type[SuccessDocument] = SuccessDocument,
        *,
        allow_login_repair: bool = True,
        **kwargs: Any,
    ) -> T | SuccessDocument:
        """Make request to the api and return response data."""

        # Alarm.com's implementation violates the JSON:API spec by sometimes returning a modified error response
        # body with a non-200 response code.
        # This response still contains an "errors" object and should validate as a FailureDocument.

        log.info(
            "Requesting %s %s with %s expecting %s as %s",
            method.upper(),
            url,
            kwargs.get("data") or kwargs.get("json"),
            accept_types,
            success_response_class.__name__,
        )

        try:
            async with self.create_request(
                method, url, accept_types, use_ajax_key=True, **kwargs
            ) as raw_resp:
                # Load the response as JSON:API object.

                response: FailureDocument | JsonApiBaseElement | MetaDocument | None = (
                    None
                )

                try:
                    response = success_response_class.from_json(await raw_resp.text())
                except json.JSONDecodeError as err:
                    # Triggered when the response is not valid JSON.
                    raise UnexpectedResponse("Response was not valid JSON.") from err
                except (ValueError, MissingField):
                    # Triggered when discriminator resolution fails or if field is missing in response.
                    pass

                if isinstance(response, success_response_class):
                    return response  # type: ignore

                # JsonAPI and AdcMini failure responses evaluate to the standard JSON:API FailureDocument.
                try:
                    response = FailureDocument.from_json(await raw_resp.text())
                except (ValueError, MissingField) as err:
                    log.exception("Failed to parse response as FailureDocument.")
                    raise UnexpectedResponse(
                        "Response did not match requested schema definition."
                    ) from err

                # "Successful" FailureDocument requests always return a 200 response code. Non-200 responses
                # indicate server failure.
                # "Successful" AdcMiniResponses requests return non-200 responses for "successful" failures like an
                # incorrect OTP code.

                if hasattr(response, "errors") and isinstance(
                    response, FailureDocument
                ):
                    # Retrieve errors from errors dict object.
                    error_codes = [
                        int(error.code)
                        for error in response.errors
                        if error.code is not None
                    ]

                    # 406: Not Authorized For Ember, 423: Processing Error
                    if any(x in error_codes for x in [406, 423]):
                        log.info(
                            "Got a processing error. This may be caused by missing permissions, being on an "
                            "Alarm.com plan without support for a particular device type, or having a "
                            "device type disabled for this system."
                        )
                        raise NotAuthorized(
                            f"Method: {method}\nURL: {url}\nStatus Codes: "
                            f"{error_codes}\nRequest Body: {kwargs.get('data')}"
                        )

                    # 401: Logged Out, 403: Invalid Anti Forgery
                    if any(x in [401, 403] for x in error_codes):
                        raise AuthenticationFailed(
                            f"Method: {method}\nURL: {url}\nStatus Codes: "
                            f"{error_codes}\nRequest Body: {kwargs.get('data')}",
                            can_autocorrect=True,
                        )

                    # 409: Two Factor Authentication Required
                    if 409 in error_codes:
                        raise AuthenticationFailed(
                            f"Two factor authentication required.\nMethod: {method}\nURL: {url}\nStatus Codes: "
                            f"{error_codes}\nRequest Body: {kwargs.get('data')}"
                        )

                    # 422: Wrong Two Factor Authentication Code
                    if 422 in error_codes:
                        raise AuthenticationFailed(
                            f"Method: {method}\nURL: {url}\nStatus Codes: "
                            f"{error_codes}\nRequest Body: {kwargs.get('data')}"
                        )

                    raise UnexpectedResponse(
                        f"Method: {method}\nURL: {url}\nStatus Codes: "
                        f"{error_codes}\nRequest Body: {kwargs.get('data')}"
                    )

                raw_resp.raise_for_status()

                # Bad things have happened if we reach this point.
                raise UnexpectedResponse

        except AuthenticationFailed as err:
            if err.can_autocorrect and allow_login_repair:
                log.info("Attempting to repair session.")
                try:
                    await self._auth_controller.login()
                    return await self.request(
                        method,
                        url,
                        success_response_class=success_response_class,
                        allow_login_repair=False,
                        **kwargs,
                    )
                except Exception as err:
                    raise AuthenticationFailed from err

            raise

    def _generate_request_url(
        self, path: ResourceType | str, id: str | set[str] | None
    ) -> str:
        """
        Generate endpoint URL for request.

        When path is a ResourceType, the URL is generated based on the resource type.
        When path is str, the path is appended to the end of the API base URL.
        """

        # Format path for appropriate resource type & pluralize.
        if isinstance(path, ResourceType):
            path = humps.camelize(path.value) + "s"
        else:
            path.rstrip("/")

        if isinstance(id, set) and len(id) == 1:
            id = id.pop()

        # Format path for single/multi/all.
        if isinstance(id, str):
            # Set path for single resource.
            path += f"/{id}"

        elif isinstance(id, set):
            # Explode IDs if id is a list.
            path += "?" + "&".join([f"ids[]={n}" for n in id])

        return f"{API_URL_BASE}{path}"

    @overload
    async def get(
        self,
        path: ResourceType | str,
        id: str,
        *,
        mini_response: Literal[False] = ...,
        **kwargs: Any,
    ) -> AdcSuccessDocumentSingle: ...

    @overload
    async def get(
        self,
        path: ResourceType | str,
        id: set[str] | None,
        *,
        mini_response: Literal[False] = ...,
        **kwargs: Any,
    ) -> AdcSuccessDocumentMulti: ...

    @overload
    async def get(
        self,
        path: str,
        id: str | None,
        *,
        mini_response: Literal[True],
        **kwargs: Any,
    ) -> AdcMiniSuccessResponse: ...

    async def get(
        self,
        path: ResourceType | str,
        id: str | set[str] | None,
        *,
        mini_response: bool = False,
        **kwargs: Any,
    ) -> AdcSuccessDocumentSingle | AdcSuccessDocumentMulti | AdcMiniSuccessResponse:
        """
            Get resources from the server.

        Args:
            id:             the id(s) of the resource(s) to get.
                            If str, get one resource.
                            If set, get specified.
                            If None, get all.
                            requests for single devices must use the single device format
                            (/devices/locks/12345-098), not the multi-device format
                            (/devices/locks?id[]=12345-098).
            path:           the path of the resource to get.
                            If ResourceType, build path based on resource type.
                            If str, use as is in place of ResourceType-generated path.
            mini_response:  whether the endpoint returns a JSON:API compliant response
                            or an Alarm.com "mini" response.
            kwargs:         additional arguments to pass to the request.

        Returns:
            AdcSuccessDocumentMulti: the response from the server.

        """

        path = self._generate_request_url(path, id)

        retries = 0
        while True:
            try:
                return await self.request(
                    method="get",
                    url=path,
                    accept_types=ResponseTypes.JSON
                    if mini_response
                    else ResponseTypes.JSONAPI,
                    success_response_class=AdcMiniSuccessResponse
                    if mini_response
                    else (
                        AdcSuccessDocumentSingle
                        if isinstance(id, str)
                        else AdcSuccessDocumentMulti
                    ),
                    **kwargs,
                )

            except (TimeoutError, aiohttp.ClientResponseError) as e:
                if retries == REQUEST_RETRY_LIMIT:
                    raise ServiceUnavailable from e
                retries += 1
                continue

    async def post(
        self,
        path: ResourceType | str,
        id: str | set[str] | None,
        action: str | None,
        *,
        mini_response: bool = False,
        **kwargs: Any,
    ) -> AdcSuccessDocumentSingle | AdcMiniSuccessResponse:
        """
        POST to server and return mashumaro deserialized AdcSuccessDocumentSingle or AdcMiniResponse.

        Convenience function that builds URLs based on resource type, ID, action, etc.
        """

        path = self._generate_request_url(path, id) + (f"/{action}" if action else "/")

        retries = 0
        while True:
            try:
                return await self.request(
                    method="post",
                    url=path,
                    accept_types=ResponseTypes.JSON
                    if mini_response
                    else ResponseTypes.JSONAPI,
                    success_response_class=AdcMiniSuccessResponse
                    if mini_response
                    else AdcSuccessDocumentSingle,
                    **kwargs,
                )

            except (TimeoutError, aiohttp.ClientResponseError) as e:
                if retries == SUBMIT_RETRY_LIMIT:
                    raise ServiceUnavailable from e
                retries += 1
                continue

    ############################
    ## RESOURCE PRETTY OUTPUT ##
    ############################

    @property
    def resources_pretty(self) -> Group:
        """Return pretty representation of resources in AlarmBridge."""

        return Group(
            *[
                x.resources_pretty
                for x in sorted(
                    self.resource_controllers, key=lambda x: x.__class__.__name__
                )
            ]
        )

    @property
    def resources_raw(self) -> Group:
        """Return raw JSON for all bridge resources."""

        return Group(
            *[
                x.resources_raw
                for x in sorted(
                    self.resource_controllers, key=lambda x: x.__class__.__name__
                )
            ]
        )