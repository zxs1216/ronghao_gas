"""Constants for the Ronghao Gas integration."""

from homeassistant.const import Platform

DOMAIN = "ronghao_gas"

CONF_API_BASE_URL = "api_base_url"
CONF_AES_KEY = "aes_key"
CONF_BEARER_TOKEN = "bearer_token"
CONF_SCAN_INTERVAL_HOURS = "scan_interval_hours"
CONF_SCAN_INTERVAL_MINUTES = "scan_interval_minutes"
CONF_USER_ID = "user_id"
CONF_USERFILES_ID = "userfiles_id"
CONF_USERINFO_ID = "userinfo_id"

DEFAULT_API_BASE_URL = "http://www.rhwxsf.com/ronghao"
DEFAULT_NAME = "荣浩燃气"
DEFAULT_SCAN_INTERVAL_HOURS = 12
SCAN_INTERVAL_HOUR_OPTIONS = (6, 8, 10, 12, 24)

DATA_COORDINATORS = "coordinators"

SERVICE_REFRESH = "refresh"
ATTR_ENTRY_ID = "entry_id"

PLATFORMS = [Platform.SENSOR]
