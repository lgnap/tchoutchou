"""Tests for the sensor module."""

from datetime import datetime
from unittest.mock import AsyncMock, Mock, patch

from tchoutchou.sensor import TchoutchouConnectionListTrainSensor
from pyrail.models import (
    ConnectionArrival,
    ConnectionDeparture,
    ConnectionDetails,
    ConnectionsApiResponse,
)
import pytest


@pytest.mark.asyncio
@patch("tchoutchou.sensor.iRail")
async def test_async_update_call_return_value_none(mock_irail) -> None:
    """Test async_update with mocked iRail."""

    mock_client = AsyncMock()
    mock_client.get_connections.return_value = None
    mock_irail.return_value.__aenter__.return_value = mock_client

    sensor = TchoutchouConnectionListTrainSensor("", "", "", 0)

    await sensor.async_update()

    mock_client.get_connections.assert_called_once()

    assert sensor.available is False


@pytest.mark.asyncio
@patch("tchoutchou.sensor.iRail")
async def test_async_update_call_return_value_empty_connection(mock_irail) -> None:
    """Tests a fully successful async_update."""

    mock_client = AsyncMock()
    mock_client.get_connections.return_value = ConnectionsApiResponse(
        version="", timestamp=datetime.now()
    )
    mock_irail.return_value.__aenter__.return_value = mock_client

    sensor = TchoutchouConnectionListTrainSensor("", "", "", 0)

    await sensor.async_update()
    assert sensor.available is False


@pytest.mark.asyncio
@patch("tchoutchou.sensor.iRail")
async def test_async_update_call_return_value_one_connection(
    mock_irail, caplog
) -> None:
    """Tests a fully successful async_update."""

    mock_client = AsyncMock()
    mock_client.get_connections.return_value = ConnectionsApiResponse(
        version="",
        timestamp=datetime.now(),
        connections=[
            ConnectionDetails(
                id="",
                duration=0,
                departure=ConnectionDeparture(
                    delay=300,  # 5'
                    station="",
                    station_info=None,
                    time=datetime.strptime("25/05/99 02:35:56", "%d/%m/%y %H:%M:%S"),
                    vehicle="IC6666",
                    vehicle_info=None,
                    platform="",
                    platform_info=None,
                    canceled=False,
                    departure_connection="",
                    direction=None,
                    left=False,
                    walking=False,
                    occupancy=None,
                ),
                arrival=ConnectionArrival(
                    delay=0,
                    station="",
                    station_info=None,
                    time=datetime.now(),
                    vehicle="",
                    vehicle_info=None,
                    platform="",
                    platform_info=None,
                    canceled=False,
                    departure_connection="",
                    direction=None,
                    arrived=False,
                    walking=False,
                ),
            )
        ],
    )
    mock_irail.return_value.__aenter__.return_value = mock_client

    sensor = TchoutchouConnectionListTrainSensor("SensorName", "From", "To", 0)

    await sensor.async_update()
    assert sensor.available is True

    assert sensor.extra_state_attributes == {
        "station_from": "From",
        "station_to": "To",
        "offset": 0,
        "vehicles": {"IC6666": "02:35 (+5)"},
    }

    #    assert sensor._state is int
