"""Constants for the Mitsubishi Electric Wi-Fi Control integration."""

DOMAIN = "melview"
MANUFACTURER = "Mitsubishi Electric"

CONF_EMAIL = "email"
CONF_PASSWORD = "password"
CONF_LOCAL = "local"
CONF_SENSOR = "sensor"

APPVERSION = "6.5.2090"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.4 Safari/605.1.15"
}
APIVERSION = 3

# Sleep timer ("PT" command). The Wi-Fi Control app only ever offers 30-minute
# steps up to 6 hours, so stay within the range it is known to accept.
SLEEP_TIMER_MAX_MINUTES = 360
SLEEP_TIMER_STEP_MINUTES = 30
