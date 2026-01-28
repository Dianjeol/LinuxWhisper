from pynput.keyboard import Key

# Standard Keyboard (F3-F10)
DICTATION = Key.f3
AI_CHAT   = Key.f4
REWRITE   = Key.f7
VISION    = Key.f8
PIN_CHAT  = Key.f9
TTS_TOGGLE = Key.f10

# Multimedia Keyboard (Apple/Media Keys)
DICTATION_ALT = 269025098
AI_CHAT_ALT   = 269025099
REWRITE_ALT   = Key.media_previous
VISION_ALT    = Key.media_play_pause
PIN_CHAT_ALT  = Key.media_next
TTS_TOGGLE_ALT = Key.media_volume_mute
