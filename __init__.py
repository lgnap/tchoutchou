"""The tchoutchou component."""

import logging

from homeassistant.core import HomeAssistant, ServiceCall

LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config):
    """Create a tchoutchou hass data && service to update track_id."""
    if "tchoutchou" not in hass.data:
        hass.data["tchoutchou"] = {}

    async def set_train_track_id(call: ServiceCall):
        """Logic to update track_id on the right entity."""
        track_id = call.data.get("track_id")
        entity_id = call.data.get("entity_id")
        LOGGER.info("Train Track ID received: %s for %s entity", track_id, entity_id)

        # Apply change on entity if into tchoutchou data (registered through sensor.py)
        entity = hass.data["tchoutchou"].get(entity_id)
        if entity:
            track_id = None if track_id == "null" else track_id
            entity.update_track_id(track_id)
        else:
            LOGGER.warning("Entity %s not found", entity_id)

    # Register service
    hass.services.async_register(
        domain="tchoutchou",
        service="set_train_track_id",
        service_func=set_train_track_id,
    )

    return True
