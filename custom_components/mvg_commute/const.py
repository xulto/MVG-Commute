from datetime import timedelta

DOMAIN = "mvg_commute"

CONF_ORIGIN = "origin"
CONF_ORIGIN_NAME = "origin_name"
CONF_DESTINATION = "destination"
CONF_DESTINATION_NAME = "destination_name"
CONF_VIA = "via"
CONF_VIA_NAME = "via_name"
CONF_WALK_MINUTES = "walk_minutes"
CONF_ACTIVE_FROM = "active_from"
CONF_ACTIVE_UNTIL = "active_until"
CONF_ACTIVE_DAYS = "active_days"

DEFAULT_WALK_MINUTES = 5
DEFAULT_ACTIVE_FROM = "06:00:00"
DEFAULT_ACTIVE_UNTIL = "10:00:00"
DEFAULT_ACTIVE_DAYS = ["mon", "tue", "wed", "thu", "fri"]
UPDATE_INTERVAL = timedelta(minutes=5)
