"""Constants for the Voice Timers integration."""

DOMAIN = "voice_timers"

# --- Config / options keys ---
CONF_TIMER_SLOTS = "timer_slots"
CONF_OVERRIDE_BUILTIN_TIMER = "override_builtin_timer"
CONF_RING_REPEAT_SECONDS = "ring_repeat_seconds"
CONF_RING_MAX_MINUTES = "ring_max_minutes"

# --- Defaults ---
# NOTE: override defaults ON per product decision — most people replacing
# the stock timer intent want it fully replaced, and the options-flow
# description makes clear how to turn it back off if they want both
# systems to coexist (named timers via this integration, unnamed/ad-hoc
# timers still handled by HA core).
DEFAULT_TIMER_SLOTS = 6
DEFAULT_OVERRIDE_BUILTIN_TIMER = True
DEFAULT_RING_REPEAT_SECONDS = 8
DEFAULT_RING_MAX_MINUTES = 5

MIN_TIMER_SLOTS = 1
MAX_TIMER_SLOTS = 20

# --- Entity / platform ---
PLATFORM = "sensor"  # each timer slot is a sensor.voice_timer_N with rich attributes
ENTITY_ID_FORMAT_SLOT = "voice_timer_{}"

# --- States (mirrors core `timer` domain state strings for familiarity) ---
STATE_IDLE = "idle"
STATE_ACTIVE = "active"

# --- Events ---
EVENT_TIMER_FINISHED = f"{DOMAIN}_finished"
EVENT_TIMER_STARTED = f"{DOMAIN}_started"
EVENT_TIMER_CANCELLED = f"{DOMAIN}_cancelled"

# --- Services ---
SERVICE_START = "start"
SERVICE_CANCEL = "cancel"
SERVICE_STOP_RINGING = "stop_ringing"

ATTR_LABEL = "label"
ATTR_MINUTES = "minutes"
ATTR_REMAINING = "remaining_seconds"
ATTR_FINISHES_AT = "finishes_at"

# --- Intents (names only — registration mechanism is a scaffolding TODO,
# see HANDOFF.md) ---
INTENT_SET_NAMED_TIMER = "VoiceTimersSetNamed"
INTENT_CANCEL_NAMED_TIMER = "VoiceTimersCancelNamed"
INTENT_TIMER_STATUS = "VoiceTimersStatus"
INTENT_STOP_RINGING = "VoiceTimersStopRinging"
