"""Number controls for Mazda 6e."""

from homeassistant.components.number import NumberEntity, NumberEntityDescription, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import MazdaApiError
from .const import DOMAIN, MAX_POLL_INTERVAL, MIN_POLL_INTERVAL
from .entity import Mazda6eEntity

POLL_INTERVAL_DESCRIPTION = NumberEntityDescription(
    key="poll_interval",
    translation_key="poll_interval",
    icon="mdi:timer-sync",
    entity_category=EntityCategory.CONFIG,
    native_min_value=MIN_POLL_INTERVAL,
    native_max_value=MAX_POLL_INTERVAL,
    native_step=30,
    native_unit_of_measurement=UnitOfTime.SECONDS,
    mode=NumberMode.BOX,
)

CHARGE_LIMIT_DESCRIPTION = NumberEntityDescription(
    key="charge_limit",
    translation_key="charge_limit",
    icon="mdi:battery-charging-80",
    entity_category=EntityCategory.CONFIG,
    native_min_value=60,
    native_max_value=100,
    native_step=1,
    native_unit_of_measurement=PERCENTAGE,
    mode=NumberMode.SLIDER,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up number controls."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    entities = [Mazda6ePollInterval(coordinator, entry)]
    entities.extend(
        Mazda6eChargeLimit(coordinator, item["vehicle"])
        for item in coordinator.data.values()
        if (item.get("status") or {}).get("charge", {}).get("maxSocPercent") is not None
        and item["vehicle"].supports("BatteryMaxSoc")
    )
    async_add_entities(entities)


class Mazda6ePollInterval(NumberEntity):
    """Control how often the integration polls the Mazda cloud API."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        self.coordinator = coordinator
        self.entity_description = POLL_INTERVAL_DESCRIPTION
        self._attr_unique_id = f"{entry.entry_id}_poll_interval"

    @property
    def suggested_object_id(self) -> str:
        """Return a stable, descriptive default entity id."""
        return f"{DOMAIN}_poll_interval"

    @property
    def native_value(self) -> int | None:
        """Return the current coordinator polling interval."""
        if self.coordinator.update_interval is None:
            return None
        return int(self.coordinator.update_interval.total_seconds())

    async def async_set_native_value(self, value: float) -> None:
        """Set the coordinator polling interval."""
        if not value.is_integer():
            raise ValueError("Poll interval must be a whole number of seconds")
        await self.coordinator.async_set_poll_interval(int(value))
        self.async_write_ha_state()


class Mazda6eChargeLimit(Mazda6eEntity, NumberEntity):
    """Represent the vehicle target state of charge."""

    def __init__(self, coordinator, vehicle) -> None:
        super().__init__(coordinator, vehicle, CHARGE_LIMIT_DESCRIPTION)

    @property
    def native_value(self) -> int | None:
        try:
            value = self.vehicle_data["status"]["charge"]["maxSocPercent"]
        except (KeyError, TypeError):
            return None
        return value if type(value) is int else None

    @property
    def available(self) -> bool:
        return super().available and bool(self.coordinator.api.control_private_key)

    async def async_set_native_value(self, value: float) -> None:
        if not value.is_integer():
            raise ValueError("Charge limit must be a whole percentage")
        charge_limit = int(value)
        try:
            await self.coordinator.api.async_set_charge_limit(
                self.vehicle.vehicle_id,
                charge_limit,
            )
        except (MazdaApiError, RuntimeError, TimeoutError) as err:
            raise HomeAssistantError(f"Mazda rejected the {self.name} command: {err}") from err
        await self.coordinator.async_refresh_until(lambda: self.native_value == charge_limit)
