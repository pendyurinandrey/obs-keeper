# CLAUDE.md

Rules for working on obs-keeper: a macOS watchdog that alerts when OBS Studio records silence.
User-facing description is in `README.md`; this file holds what the code does not show.

## Language

Code, comments, docstrings, README and this file are in English. The UI and alert texts are
bilingual (English, Russian) via `obs_keeper/i18n.py`. Conversation with the maintainer is in Russian.
After changing behaviour or config keys, update `README.md` (status table, configuration table).

## Layout

| Module | Responsibility |
|---|---|
| `detector.py` | Pure state machine: samples in, transitions out (`lost`, `reminder`, `recovered`, `remediate`). No I/O, threads or clocks; callers pass `now`. |
| `monitor.py` | Owns the OBS connection thread, feeds the detector, delivers alerts, runs self-healing, publishes `Status`. |
| `obs_client.py` | The only place that imports `obsws-python`. Turns events into `ObsSink` calls. |
| `alerts.py` | macOS channels (`osascript`, `afplay`, `say`) with an injectable runner. |
| `config.py` | Dataclasses + tolerant JSON load/save + `validate()`. |
| `credentials.py` | OBS password: env var, then keychain. |
| `i18n.py` | Translations, `tr()`, `format_duration()`. |
| `cli.py` | `obs-keeper` entry point. |

Policy (when to alert, repeat, heal) belongs in `detector.py`; keep `monitor.py` free of it.
Detection logic must stay testable without OBS.

## Rules

1. **Never log or print the OBS password.** `obsws-python` logs `password='...'` at INFO;
   `obs_client.py` pins that logger to WARNING and `tests/test_obs_client.py` guards it. The password
   lives in the keychain or `OBS_KEEPER_PASSWORD`, never in `config.json`.
2. **Detect by timestamps, not by last level.** An input that stops reporting must alert like a silent
   one (`reason == "no_data"`). Do not store "current level" and poll it.
3. **No shell for alerts.** Commands are argv lists; notification text is passed as AppleScript `argv`,
   never spliced into the script. Sound and voice names are validated.
4. **Alerts are best effort.** A failing alert or self-heal must never stop the watchdog.
5. **Every user-visible string goes through `i18n.py`** with both languages; `tests/test_i18n.py`
   enforces equal keys and placeholders.
6. **New config key**: dataclass field in `config.py`, validation if needed, README table row, a test.
7. Blocking OBS requests only from the monitor's worker thread; event callbacks only touch the detector
   under `Monitor._lock`.
8. Qt (PySide6) is imported only inside the UI package, never by core modules, so tests and the
   headless `run` work without it. UI code holds no logic: it edits `Config` and renders `Status`.

## Pitfalls

- **`obsws-python` event thread dies silently** when the socket closes; liveness is checked with
  `ObsConnection.alive()` plus a periodic `ping()`.
- **Wrong password** surfaces as `OBSSDKError("failed to identify client...")`, not as a closed-socket
  error; `obs_client.py` maps it to `ObsError("auth")`.
- `InputVolumeMeters` is a high-volume event and must be requested explicitly
  (`Subs.INPUTVOLUMEMETERS`); a test checks the subscription reaches the server.
- Event handlers are matched by function `__name__` (`on_<snake_case_event>`); register bound methods,
  not an object.
- **Volume meters may not equal what gets recorded.** The meter follows the source, the recording
  follows the audio mixer. If a real outage shows silence in the file but a live meter, add a
  file-based check (see Ideas) instead of trusting the meter.
- **Self-healing is unverified.** Hiding/showing the scene item may not re-create the ScreenCaptureKit
  stream. Verify on a live OBS by watching for a new `captureSession` in
  `log show --predicate 'process == "replayd"'`.
- macOS BSD `sed -i` needs a suffix argument (`sed -i ''`); prefer editing files with proper tools.

## Testing

```shell
pip install -e ".[dev]"
python -m pytest
```

Tests mirror the code: `tests/test_<module>.py`. `tests/fake_obs.py` is a minimal obs-websocket v5
server (password handshake, a few requests, pushed events) used by `test_obs_connection.py` with the
real `obsws-python`. Tests must not make noise: inject the alert runner. CI (`.github/workflows/tests.yml`)
runs pytest on Python 3.10 and 3.12; no skipped tests allowed.

## Ideas (not started)

- Second detection layer independent of OBS meters: probe the growing recording file with ffmpeg.
- Phone push (e.g. ntfy) as an extra alert channel.
- Launch at login (LaunchAgent).
