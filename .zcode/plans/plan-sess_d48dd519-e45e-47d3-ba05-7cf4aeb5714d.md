## Problem

"Lights not related to the entertainment zone should not be synced with it."

**Video sync already does the right thing** — `SyncController._update_lights()` (`src/lumux/sync.py:303-340`) only sends to channels of the selected entertainment config, so non-zone lights are never touched there.

**The leak is in Reading Mode.** `ReadingModeController._get_target_light_ids()` (`src/lumux/reading_mode.py:194-196`) falls back to `self.bridge.get_light_ids()` — i.e. **every light on the bridge** — whenever:
- no explicit `light_ids` are set (the default `[]`, which isn't even exposed in the GUI), and
- the entertainment-config lookup returns no members, throws, or there's no `entertainment_config_id`.

Because `reading_mode.auto_activate` defaults to `true`, this fallback can silently drive unrelated lights right after video sync stops.

## Fix (single file)

**`src/lumux/reading_mode.py` — `_get_target_light_ids()`**

Replace the all-lights fallback (lines 194-196) with a no-op + clear log, so the resolution order is:
1. Explicit `self._target_light_ids` if set → use them *(kept as opt-in override / escape hatch)*
2. Else, lights from the entertainment config's `channels[].members` → use them *(the zone)*
3. Else → return `[]` and log that no zone lights were found — **never** fall back to all bridge lights

```python
        # Before (leak):
        # Fallback: use all known lights
        if hasattr(self.bridge, 'get_light_ids'):
            return self.bridge.get_light_ids()
        return []

        # After:
        timed_print(
            "Reading mode: No lights found in the entertainment zone; "
            "not syncing any lights outside the zone"
        )
        return []
```

## Behavior after change
- **Reading mode with an entertainment zone configured** → only the zone's lights receive the static color (same as the common path today).
- **Reading mode when the zone lookup fails / zone is empty / no zone configured** → does nothing and logs a clear message, instead of lighting up unrelated bulbs. Matches the request literally.
- **Explicit `reading_mode.light_ids` override** still works (unchanged) for anyone who genuinely wants a specific set.
- **Video sync** — unchanged (already zone-scoped).

## Notes / out of scope
- The zone lookup (`get_entertainment_configuration`) reads the config definition via GET, which is valid even after streaming is deactivated — so this still works when reading mode disconnects the stream before activating.
- The legacy `ZoneMapping` REST path is unused in the live sync loop, so no change there.
- No tests exist for `reading_mode.py`; verification is manual (confirm non-zone lights stay off when reading mode activates with `auto_activate`).
- No settings schema change, no default file change, no other files touched.