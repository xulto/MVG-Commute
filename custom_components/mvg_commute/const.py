from datetime import timedelta

DOMAIN = "mvg_commute"

CONF_ORIGIN = "origin"
CONF_ORIGIN_NAME = "origin_name"
CONF_DESTINATION = "destination"
CONF_DESTINATION_NAME = "destination_name"
CONF_VIA = "via"
CONF_VIA_NAME = "via_name"
CONF_WALK_MINUTES = "walk_minutes"

DEFAULT_WALK_MINUTES = 5
UPDATE_INTERVAL = timedelta(minutes=2)
