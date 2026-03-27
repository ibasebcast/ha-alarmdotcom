"""Config flow to configure Alarmdotcom."""

import logging
from typing import TYPE_CHECKING, Any, Literal

import aiohttp
import asyncio
import pyalarmdotcomajax as pyadc
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import selector
from homeassistant.helpers.selector import (
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .const import (
    CONF_ARM_AWAY,
    CONF_ARM_CODE,
    CONF_ARM_HOME,
    CONF_ARM_MODE_OPTIONS,
    CONF_ARM_NIGHT,
    CONF_MFA_TOKEN,
    CONF_OPTIONS_DEFAULT,
    CONF_OTP,
    CONF_OTP_METHOD,
    CONF_OTP_METHODS_LIST,
    CONF_REMOVE_ARM_CODE,
    DOMAIN,
)

if TYPE_CHECKING:
    from .hub import AlarmHub

LOGGER = logging.getLogger(__name__)
LegacyArmingOptions = Literal["home", "away", "true", "false"]


class ADCFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle an Alarmdotcom config flow."""

    VERSION = 4

    def __init__(self) -> None:
        """Initialize the Alarmdotcom flow."""
        self.config: dict[str, Any] = {}
        self.system_id: str | None = None
        self.sensor_data: dict[str, Any] | None = None
        self._config_title: str | None = None
        self.bridge: pyadc.AlarmBridge | None = None
        self._existing_entry: config_entries.ConfigEntry | None = None
        self._otp_options: pyadc.OtpRequired | None = None
        self.otp_method: pyadc.OtpType | None = None

    @staticmethod
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> "ADCOptionsFlowHandler":
        """Tell Home Assistant that this integration supports configuration options."""
        return ADCOptionsFlowHandler(config_entry)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Gather configuration data when flow is initiated via the user interface."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self.config = {
                CONF_USERNAME: user_input[CONF_USERNAME],
                CONF_PASSWORD: user_input[CONF_PASSWORD],
                CONF_MFA_TOKEN: user_input.get(CONF_MFA_TOKEN),
            }

            LOGGER.debug("Logging in to Alarm.com...")

            self.bridge = pyadc.AlarmBridge(
                username=self.config[CONF_USERNAME],
                password=self.config[CONF_PASSWORD],
                mfa_token=self.config[CONF_MFA_TOKEN],
            )

            async with asyncio.timeout(60):
                try:
                    await self.bridge.login()
                except pyadc.OtpRequired as exc:
                    LOGGER.debug("OTP code required. Moving to selection step.")
                    self._otp_options = exc
                    return await self.async_step_otp_select_method()
                except pyadc.MustConfigureMfa:
                    return self.async_abort(reason="must_enable_2fa")
                except (
                    TimeoutError,
                    aiohttp.ClientError,
                    pyadc.UnexpectedResponse,
                    pyadc.NotAuthorized,
                ):
                    LOGGER.exception("User login failed to contact Alarm.com.")
                    errors["base"] = "cannot_connect"
                except pyadc.AuthenticationFailed:
                    errors["base"] = "invalid_auth"
                except Exception:
                    LOGGER.exception("Got error while initializing Alarm.com.")
                    errors["base"] = "unknown"
                else:
                    return await self.async_step_final()

        creds_schema = vol.Schema(
            {
                vol.Required(CONF_USERNAME): TextSelector(
                    TextSelectorConfig(
                        type=TextSelectorType.TEXT,
                        autocomplete="username",
                    )
                ),
                vol.Required(CONF_PASSWORD): TextSelector(
                    TextSelectorConfig(
                        type=TextSelectorType.PASSWORD,
                        autocomplete="current-password",
                    )
                ),
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=creds_schema,
            errors=errors,
            last_step=False,
        )

    async def async_step_otp_select_method(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Select OTP method when integration configured through UI."""
        if not self._otp_options:
            return self.async_abort(reason="no_otp_options")

        enabled_methods = self._otp_options.enabled_2fa_methods
        if not enabled_methods:
            return self.async_abort(reason="no_otp_options")

        errors: dict[str, str] = {}

        # Sensible auto skip:
        # if authenticator app is the ONLY method, nothing needs to be sent.
        # For SMS or email, always show the selector so request_otp() is triggered.
        if (
            user_input is None
            and len(enabled_methods) == 1
            and enabled_methods[0] == pyadc.OtpType.app
        ):
            self.otp_method = enabled_methods[0]
            LOGGER.debug(
                "Only authenticator app is enabled. Skipping method selection."
            )
            return await self.async_step_otp_submit()

        if user_input is not None:
            selected_name = user_input[CONF_OTP_METHOD]
            self.otp_method = getattr(pyadc.OtpType, selected_name.lower(), None)

            if not self.otp_method:
                errors["base"] = "invalid_otp_method"
            else:
                try:
                    if self.otp_method in (pyadc.OtpType.email, pyadc.OtpType.sms):
                        LOGGER.debug(
                            "Requesting OTP via %s...", self.otp_method.name
                        )
                        await self.bridge.auth_controller.request_otp(self.otp_method)

                    return await self.async_step_otp_submit()

                except (
                    TimeoutError,
                    aiohttp.ClientError,
                    pyadc.UnexpectedResponse,
                    pyadc.NotAuthorized,
                ):
                    LOGGER.exception("Failed to request OTP.")
                    errors["base"] = "cannot_connect"
                except Exception:
                    LOGGER.exception("Unexpected error while requesting OTP.")
                    errors["base"] = "unknown"

        otp_method_schema = vol.Schema(
            {
                vol.Required(
                    CONF_OTP_METHOD,
                    default=enabled_methods[0].name if enabled_methods else None,
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=[m.name for m in enabled_methods],
                        mode=SelectSelectorMode.DROPDOWN,
                        translation_key=CONF_OTP_METHODS_LIST,
                    )
                ),
            }
        )

        return self.async_show_form(
            step_id="otp_select_method",
            data_schema=otp_method_schema,
            errors=errors,
            last_step=False,
        )

    async def async_step_otp_submit(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Gather OTP when integration configured through UI."""
        errors: dict[str, str] = {}

        if user_input is not None:
            if not self.otp_method:
                return self.async_abort(reason="otp_method_lost")

            try:
                mfa_cookie = await self.bridge.auth_controller.submit_otp(
                    method=self.otp_method,
                    code=user_input[CONF_OTP],
                    device_name=f"Home Assistant {self.hass.config.location_name}",
                )

                if mfa_cookie:
                    self.config[CONF_MFA_TOKEN] = mfa_cookie
                    return await self.async_step_final()

                errors["base"] = "invalid_otp"

            except pyadc.AuthenticationFailed:
                errors["base"] = "invalid_otp"
            except (
                TimeoutError,
                aiohttp.ClientError,
                pyadc.UnexpectedResponse,
                pyadc.NotAuthorized,
            ):
                LOGGER.exception("OTP submission failed.")
                errors["base"] = "cannot_connect"
            except Exception:
                LOGGER.exception("Unexpected error during OTP submission.")
                errors["base"] = "unknown"

        creds_schema = vol.Schema(
            {
                vol.Required(CONF_OTP): TextSelector(
                    TextSelectorConfig(
                        type=TextSelectorType.TEXT,
                        autocomplete="one-time-code",
                    )
                ),
            }
        )

        return self.async_show_form(
            step_id="otp_submit",
            data_schema=creds_schema,
            errors=errors,
            last_step=True,
        )

    async def async_step_final(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Create configuration entry using entered data."""
        await self.bridge.fetch_full_state()

        system_id = str(self.bridge.active_system.id)
        await self.async_set_unique_id(system_id)

        self._config_title = (
            f"{self.bridge.active_system.name} "
            f"({self.bridge.auth_controller.user_email})"
        )

        if self._existing_entry:
            self.hass.config_entries.async_update_entry(
                self._existing_entry,
                data=self.config,
            )
            await self.hass.config_entries.async_reload(
                self._existing_entry.entry_id
            )
            return self.async_abort(reason="reauth_successful")

        return self.async_create_entry(
            title=self._config_title,
            data=self.config,
            options=CONF_OPTIONS_DEFAULT,
        )

    async def async_step_reauth(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Perform reauth upon an API authentication error."""
        self._existing_entry = self.hass.config_entries.async_get_entry(
            self.context["entry_id"]
        )
        return await self.async_step_reauth_confirm(user_input)

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Dialog that informs the user that reauth is required."""
        if user_input is None:
            return self.async_show_form(
                step_id="reauth_confirm",
                data_schema=vol.Schema({}),
            )
        return await self.async_step_user()


class ADCOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle option configuration via Integrations page."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.options = dict(config_entry.options)

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """First screen for configuration options. Sets arming code."""
        if user_input is not None:
            if user_input[CONF_REMOVE_ARM_CODE]:
                user_input[CONF_ARM_CODE] = ""
            self.options.update(user_input)
            self.options.pop(CONF_REMOVE_ARM_CODE, None)
            return await self.async_step_modes()

        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_ARM_CODE,
                    default=self.options.get(CONF_ARM_CODE, ""),
                ): selector.selector({"text": {"type": "password"}}),
                vol.Optional(
                    CONF_REMOVE_ARM_CODE,
                    default=False,
                ): selector.selector({"boolean": {}}),
            }
        )

        return self.async_show_form(step_id="init", data_schema=schema)

    async def async_step_modes(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Set arming mode profiles."""
        if user_input is not None:
            self.options.update(user_input)
            return self.async_create_entry(title="", data=self.options)

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_ARM_HOME,
                    default=self.options.get(
                        CONF_ARM_HOME,
                        CONF_OPTIONS_DEFAULT[CONF_ARM_HOME],
                    ),
                ): cv.multi_select(CONF_ARM_MODE_OPTIONS),
                vol.Required(
                    CONF_ARM_AWAY,
                    default=self.options.get(
                        CONF_ARM_AWAY,
                        CONF_OPTIONS_DEFAULT[CONF_ARM_AWAY],
                    ),
                ): cv.multi_select(CONF_ARM_MODE_OPTIONS),
                vol.Required(
                    CONF_ARM_NIGHT,
                    default=self.options.get(
                        CONF_ARM_NIGHT,
                        CONF_OPTIONS_DEFAULT[CONF_ARM_NIGHT],
                    ),
                ): cv.multi_select(CONF_ARM_MODE_OPTIONS),
            }
        )

        return self.async_show_form(
            step_id="modes",
            data_schema=schema,
            last_step=True,
        )