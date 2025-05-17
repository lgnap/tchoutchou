"""Get tchoutchou connections && tracking."""

from __future__ import annotations

import logging
import os
import time
from zoneinfo import ZoneInfo

from pyrail import iRail
import voluptuous as vol

from homeassistant.components.sensor import (
    PLATFORM_SCHEMA as SENSOR_PLATFORM_SCHEMA,
    SensorEntity,
)
from homeassistant.const import UnitOfTime
from homeassistant.core import HomeAssistant
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
import homeassistant.util.dt as dt_util

LOGGER = logging.getLogger(__name__)

API_FAILURE = -1

CONNECTIONS_NAME = "Tchoutchou connections"
TRACKING_NAME = "Tchoutchou tracking"

# configuration keys (for configuration.yaml)
CONF_STATION_FROM = "station_from"
CONF_STATION_TO = "station_to"
CONF_STATION_WARN = "station_warn"
# When you call connections we could like an offset (to have trains in past, if you're already into)
# This expressed in minutes (- will be in the past, + in the future)
CONF_OFFSET = "offset"
# After a certain time_until you should disable the vehicle tracking (same rules than offset)
CONF_DISABLE_TRACKING_TIME = "disable_tracking_time_until"

# Setup default timezone
# Not really sure that what is really needed but it's working like that...
DEFAULT_TZ = ZoneInfo("Europe/Paris")
os.environ["TZ"] = "Europe/Paris"
time.tzset()

PLATFORM_SCHEMA = SENSOR_PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_STATION_FROM): cv.string,
        vol.Required(CONF_STATION_TO): cv.string,
        vol.Optional(CONF_STATION_WARN, default=""): cv.string,
        vol.Optional(CONF_OFFSET, default=0): int,
        vol.Optional(CONF_DISABLE_TRACKING_TIME, default=10): int,
    }
)


def get_time_until(epoch_time: int):
    """Calculate the time between now and a epoch time."""
    delta = dt_util.utc_from_timestamp(epoch_time) - dt_util.now(DEFAULT_TZ)
    return round(delta.total_seconds() / 60)


def get_delay_in_minutes(delay=0):
    """Get the delay in minutes from a delay in seconds."""
    return round(int(delay) / 60)


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType,
) -> None:
    """Get config && set up Tchoutchou sensors."""

    station_from = config[CONF_STATION_FROM]
    station_to = config[CONF_STATION_TO]
    station_warn = config[CONF_STATION_WARN]
    offset = config[CONF_OFFSET]
    disable_tracking_time = config[CONF_DISABLE_TRACKING_TIME]

    connectionList = TchoutchouConnectionListTrainSensor(
        CONNECTIONS_NAME, station_from, station_to, offset
    )
    tracking = TchoutchouVehicleTrackSensor(
        TRACKING_NAME,
        station_from,
        station_to,
        [station_from, station_warn, station_to],
        disable_tracking_time,
    )
    sensors: list[SensorEntity] = [
        connectionList,
        tracking,
    ]

    # Record tracking entity to "action" it through services
    entity_id = f"sensor.{(TRACKING_NAME).lower().replace(' ', '_')}"
    if "tchoutchou" not in hass.data:
        hass.data["tchoutchou"] = {}
    hass.data["tchoutchou"][entity_id] = tracking

    async_add_entities(sensors, True)

    return True


# -----------------------------------------------------------
# -----------------------------------------------------------
# -----------------------------------------------------------
# CLASS DELIMITATION
# TchoutchouVehicleTrackSensor
# CLASS DELIMITATION
# -----------------------------------------------------------
# -----------------------------------------------------------
# -----------------------------------------------------------


class TchoutchouVehicleTrackSensor(SensorEntity):
    """Get tracking for a train."""

    def __init__(
        self,
        name,
        station_from: str,
        station_to: str,
        stations_watch: list,
        disable_tracking_time: int,
    ) -> None:
        """Initialize the Tchoutchou connection sensor."""
        self._track_id = None
        self._tracking = {}
        self._name = name
        self._at_from = None
        self._at_to = None
        self._into_to = None
        # Stations watch is an array with stations: from, to & warn
        # seems to be counterproductive but this drives the stations written into tracking
        # only stations from, to are root attributes into sensor to be used directely by HA automation
        self._station_from = station_from
        self._station_to = station_to
        self._stations_watch = stations_watch
        self._disable_tracking_time = disable_tracking_time
        self._state = "no_track"

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._name

    @property
    def icon(self):
        """Return the sensor icon."""
        return "mdi:train"

    def update_track_id(self, track_id):
        """Set up Track ID and adapt state."""
        self._track_id = track_id

        if track_id is None:
            self._state = "no_track"
        else:
            self._state = "tracking"
            self.hass.async_create_task(self.async_update())

        self.schedule_update_ha_state()

    @property
    def extra_state_attributes(self):
        """Return sensor attributes if data is available."""
        """State with no track mean => disable all"""
        """So you must check state before anything else"""
        if self._state == "no_track":
            return None

        return {
            "track_id": self._track_id,
            "tracking": self._tracking,
            "station_from": self._station_from,
            "station_to": self._station_to,
            "at_from": self._at_from,
            "at_to": self._at_to,
            "into_to": self._into_to,
        }

    @property
    def native_value(self):
        """Return the state of the device."""
        return self._state

    async def async_update(self) -> None:
        """Update tracking data if track id is defined."""
        if self._state == "no_track":
            return

        async with iRail(lang="fr") as api_client:
            vehicle_tracked = await api_client.get_vehicle(id=self._track_id)

            self._tracking = {}

            if not (vehicle_tracked):
                LOGGER.warning(
                    "API returned invalid vehicle_tracked: %r", vehicle_tracked
                )
                return

            # get stops for the vehicle
            for stop in vehicle_tracked.stops:
                station_name = stop.station
                # Handle only stations_watch list
                if station_name in self._stations_watch:
                    # format time
                    into_min = get_time_until(stop.time.timestamp())
                    hhmm_time = stop.time.strftime("%H:%M")

                    # update at_from on from station
                    if station_name == self._station_from:
                        self._at_from = hhmm_time

                    # update at_to, into_to on to station
                    if station_name == self._station_to:
                        self._into_to = into_min
                        self._at_to = hhmm_time

                        # Vehicle is at/passed station_to for disable_tracking_time, stop tracking it
                        if into_min < -self._disable_tracking_time:
                            LOGGER.warning(
                                "Train into %d min (%d), auto disable tracking",
                                -self._disable_tracking_time,
                                into_min,
                            )
                            self.update_track_id(None)

                    # write into tracking item
                    self._tracking[station_name] = {
                        "is_left": stop.left,
                        "is_arrived": stop.arrived,
                        "at": hhmm_time,
                        "into": str(into_min) + " min",
                    }

            self.async_write_ha_state()


# -----------------------------------------------------------
# -----------------------------------------------------------
# -----------------------------------------------------------
# CLASS DELIMITATION
# TchoutchouConnectionListTrainSensor
# CLASS DELIMITATION
# -----------------------------------------------------------
# -----------------------------------------------------------
# -----------------------------------------------------------


class TchoutchouConnectionListTrainSensor(SensorEntity):
    """Get the list of the next trains for a connection."""

    _attr_attribution = "https://api.irail.be/"
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES

    def __init__(self, name, station_from, station_to, offset) -> None:
        """Initialize the Tchoutchou connection sensor."""
        self._name = name
        self._offset = offset
        self._station_from = station_from
        self._station_to = station_to

        self._connections = []
        self._state = None

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._name

    @property
    def icon(self):
        """Return the sensor icon."""
        return "mdi:train"

    @property
    def extra_state_attributes(self):
        """Return sensor attributes if data is available."""
        if self._state is None or not self._connections:
            return None

        train_attrs = {}
        for connection in self._connections:
            hhmm_time = connection.departure.time.astimezone(DEFAULT_TZ).strftime(
                "%H:%M"
            )

            delay = get_delay_in_minutes(connection.departure.delay)

            # uniform formatting for vehicle time (to get enough space into buttons)
            vehicle_time = (
                f"{hhmm_time} ({delay:+02d})" if delay > 0 else f"  {hhmm_time}   "
            )

            train_attrs[connection.departure.vehicle] = vehicle_time

        return {
            "station_from": self._station_from,
            "station_to": self._station_to,
            "vehicles": train_attrs,
        }

    @property
    def native_value(self):
        """Return the state of the device."""
        return self._state

    async def async_update(self) -> None:
        """Set the state to the duration of a connection."""

        time_now = int(time.time())
        time_with_offset = time_now + (60 * self._offset)
        time_ask = time.localtime(time_with_offset)
        time_ask_string = time.strftime("%H%M", time_ask)

        LOGGER.debug("clock time asked: %s", time_ask_string)

        async with iRail(lang="fr") as api_client:
            api_connections = await api_client.get_connections(
                self._station_from, self._station_to, time=time_ask_string
            )

            if api_connections == API_FAILURE:
                LOGGER.warning("API failed in TchoutchouSensor")
                return

            if not (connections := api_connections.connections):
                LOGGER.warning("API returned invalid connection: %r", api_connections)
                return

            # LOGGER.debug("API returned connection: %r", connection)

            self._connections = connections[0:4]

            self._state = api_connections.timestamp.timestamp()
