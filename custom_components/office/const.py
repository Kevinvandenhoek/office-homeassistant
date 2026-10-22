"""Constants for Office."""

DOMAIN = "office"

CONF_ROLE = "role"
ROLE_HOST = "host"
ROLE_MEMBER = "member"
CONF_NAME = "name"
CONF_URL = "url"
CONF_TOKEN = "token"

# Options: the office days on the host, and the notification settings in every house.
CONF_OFFICE_DAYS = "office_days"
CONF_NOTIFY = "notify"
CONF_PHONE = "phone"
CONF_MORNING = "morning"
CONF_UNTIL = "until"
DEFAULTS = {CONF_NOTIFY: True, CONF_PHONE: None, CONF_MORNING: "07:30", CONF_UNTIL: "12:00"}
NO_PHONE = "None"

API_PATH = "/api/office/v1"
STATIC_PATH = "/office_static"
HUB_STORE = "office.hub"
SEEN_STORE = "office.seen"
TITLE = "Skip day"
