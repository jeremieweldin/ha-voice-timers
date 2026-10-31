"""Constants for the Voice Timers integration."""

DOMAIN = "voice_timers"

# --- Config / options keys ---
CONF_TIMER_SLOTS = "timer_slots"
CONF_OVERRIDE_BUILTIN_TIMER = "override_builtin_timer"
CONF_RING_REPEAT_SECONDS = "ring_repeat_seconds"
CONF_RING_MAX_MINUTES = "ring_max_minutes"
# Optional list of assist_satellite entity_ids to announce on. Empty/unset
# means "every satellite" (mirrors the original YAML package's behavior).
CONF_ANNOUNCE_TARGETS = "announce_targets"

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

# --- Satellite announcements ---
ANNOUNCE_DOMAIN = "assist_satellite"
ANNOUNCE_SERVICE = "announce"

# --- Custom sentences ---
# The default conversation agent only loads sentences from the built-in
# intents package and from <config>/custom_sentences/<lang>/. Custom
# components are NOT scanned, and async_register_sentence() was removed in
# HA 2025.10.1 — so the integration writes its sentence YAML here at setup
# and calls conversation.reload. See __init__.py.
SENTENCES_LANGUAGE = "en"
SENTENCES_DIR = "custom_sentences"
SENTENCES_FILENAME = "voice_timers.yaml"
CONVERSATION_DOMAIN = "conversation"
CONVERSATION_RELOAD_SERVICE = "reload"

# hassil list names referenced by the generated sentences.
LIST_LABEL = "vt_label"
LIST_MINUTES = "vt_minutes"
MINUTES_RANGE_MIN = 1
MINUTES_RANGE_MAX = 600

# --- Dispatcher ---
# Signal fired (with entry_id) whenever any slot/ringing state changes, so
# sensor entities can re-render without polling.
SIGNAL_STATE_UPDATED = f"{DOMAIN}_state_updated"

# --- States (mirrors core `timer` domain state strings for familiarity) ---
STATE_IDLE = "idle"
STATE_ACTIVE = "active"
STATE_PAUSED = "paused"

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

# --- Intents ---
# Handlers registered in intent.py; the sentences that map to these are
# written to custom_sentences/en/ by sentences.py (both reference these names).
INTENT_SET_NAMED_TIMER = "VoiceTimersSetNamed"
INTENT_CANCEL_NAMED_TIMER = "VoiceTimersCancelNamed"
INTENT_TIMER_STATUS = "VoiceTimersStatus"
INTENT_STOP_RINGING = "VoiceTimersStopRinging"
