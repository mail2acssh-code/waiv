"""
Detects whether any media is currently playing on the system.
Checks in priority order:
  1. Spotify (native AppleScript)
  2. Apple Music (native AppleScript)
  3. Any browser tab playing audio (via System Events window titles heuristic)
  4. System audio output active (CoreAudio, via osascript)

Returns True if something is playing → gesture loop runs at full speed.
Returns False → gesture loop sleeps to save CPU/battery.
"""

import subprocess
import logging

log = logging.getLogger(__name__)

# Cache result for this many seconds before re-checking
_CACHE_TTL = 2.0

import time
_cache_value = False
_cache_time = 0.0


def _osascript(script: str) -> str:
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=2
        )
        return result.stdout.strip()
    except Exception:
        return ""


def _spotify_open() -> bool:
    """True if the Spotify app process is running (assumes it's playing)."""
    result = _osascript(
        'tell application "System Events" to '
        '(name of processes) contains "Spotify"'
    )
    return result == "true"


def _music_playing() -> bool:
    result = _osascript(
        'tell application "System Events" to '
        '(name of processes) contains "Music"'
    )
    if result != "true":
        return False
    state = _osascript(
        'tell application "Music" to player state as string'
    )
    return state == "playing"


def _browser_media_open() -> bool:
    """
    Check if any browser has a media URL open (YouTube, Netflix, etc.).
    Uses URL matching — `audible` is unreliable across Chrome versions.
    If a media URL is open we treat the browser as active so gestures stay
    live; the actual video state is controlled via media keys / JS.
    """
    MEDIA_DOMAINS = ("youtube.com", "netflix.com", "music.apple.com",
                     "soundcloud.com", "tidal.com", "primevideo.com",
                     "twitch.tv", "vimeo.com")

    chrome_script = """
        tell application "System Events"
            if not ((name of processes) contains "Google Chrome") then return "false"
        end tell
        tell application "Google Chrome"
            repeat with w in windows
                repeat with t in tabs of w
                    set tabURL to URL of t
                    {conditions}
                end repeat
            end repeat
        end tell
        return "false"
    """.format(conditions="\n                    ".join(
        f'if tabURL contains "{d}" then return "true"'
        for d in MEDIA_DOMAINS
    ))

    if _osascript(chrome_script) == "true":
        return True

    safari_script = """
        tell application "System Events"
            if not ((name of processes) contains "Safari") then return "false"
        end tell
        tell application "Safari"
            repeat with w in windows
                repeat with t in tabs of w
                    set tabURL to URL of t
                    {conditions}
                end repeat
            end repeat
        end tell
        return "false"
    """.format(conditions="\n                    ".join(
        f'if tabURL contains "{d}" then return "true"'
        for d in MEDIA_DOMAINS
    ))

    if _osascript(safari_script) == "true":
        return True

    return False


def _system_audio_playing() -> bool:
    """
    Fallback: check if system audio output volume is non-zero and not muted.
    This is a weak signal (doesn't confirm audio is actively playing).
    Only used as last resort.
    """
    result = _osascript("output muted of (get volume settings)")
    if result == "true":
        return False
    # We can't reliably detect active audio output without private APIs,
    # so return False here — rely on app-specific checks above.
    return False


def is_playing() -> bool:
    """
    Returns True if any recognized media source is actively playing.
    Result is cached for _CACHE_TTL seconds to avoid hammering osascript.
    """
    global _cache_value, _cache_time

    now = time.monotonic()
    if now - _cache_time < _CACHE_TTL:
        return _cache_value

    playing = (
        _spotify_open()
        or _music_playing()
        or _browser_media_open()
    )

    _cache_value = playing
    _cache_time = now
    log.debug("Media playing: %s", playing)
    return playing
