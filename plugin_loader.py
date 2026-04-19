"""
Waiv Plugin Loader — discovers and merges gesture actions from plugins/.

Plugin protocol (any .py file in the plugins/ directory):

  GESTURE_ACTIONS = {
      "thumbs_up":  my_function,   # required
      ...
  }

  def is_active() -> bool:         # optional
      '''Return False to skip this plugin right now.'''
      ...

Merge order
-----------
Pass 1 — plugins WITHOUT is_active() (unconditional defaults, e.g. media_player)
Pass 2 — plugins WITH is_active() that return True (app-specific overrides)

Later entries in each pass override earlier ones (alphabetical load order).
This means an app-specific plugin cleanly overrides media_player for any
gestures it claims, and automatically falls back to media_player when the
app is not running.
"""

import importlib
import logging
import os
import pkgutil

log = logging.getLogger(__name__)

_PLUGINS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "plugins")
_loaded: list = []   # imported plugin modules, populated once on first call


def _load_plugins() -> None:
    global _loaded
    if _loaded:
        return
    for _finder, name, _is_pkg in pkgutil.iter_modules([_PLUGINS_DIR]):
        if name.startswith("_"):
            continue
        try:
            mod = importlib.import_module(f"plugins.{name}")
            _loaded.append(mod)
            log.debug("Loaded plugin: %s", name)
        except Exception as exc:
            log.warning("Failed to load plugin %r: %s", name, exc)


def get_action(gesture: str):
    """
    Return the callable for *gesture*, re-evaluating is_active() every call
    so plugins respond instantly to apps being launched or quit.
    Returns None if no plugin handles the gesture.
    """
    _load_plugins()

    merged: dict = {}

    # Pass 1: unconditional plugins (no is_active defined)
    for mod in _loaded:
        if not hasattr(mod, "is_active") and hasattr(mod, "GESTURE_ACTIONS"):
            merged.update(mod.GESTURE_ACTIONS)

    # Pass 2: conditional plugins (is_active() must return True)
    for mod in _loaded:
        if hasattr(mod, "is_active") and hasattr(mod, "GESTURE_ACTIONS"):
            try:
                if mod.is_active():
                    merged.update(mod.GESTURE_ACTIONS)
            except Exception as exc:
                log.warning("Plugin %r is_active() raised: %s", mod.__name__, exc)

    return merged.get(gesture)
