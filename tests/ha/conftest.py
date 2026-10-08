import pytest
from homeassistant.core import HomeAssistant


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


@pytest.fixture(autouse=True)
async def munich_time_zone(hass: HomeAssistant):
    await hass.config.async_set_time_zone("Europe/Berlin")
