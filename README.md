# obs-keeper

A small watchdog for [OBS Studio](https://obsproject.com/) on macOS that tells you when the audio
of a recording goes silent, so you notice in minutes instead of hours.

## Why

On 2026-09-21 a 2.5-hour screen recording lost its sound at 57:30 and nobody noticed until the
end. The macOS side (ScreenCaptureKit) kept delivering audio the whole time; OBS itself stopped
passing it on and wrote digital silence. Stopping and restarting the recording did not help, only
restarting OBS did. OBS has no built-in warning for this, so `obs-keeper` provides one.

## How it works

`obs-keeper` connects to OBS through its built-in
[WebSocket server](https://github.com/obsproject/obs-websocket) and subscribes to the audio level
meters of every input. While OBS is recording, it tracks *the time of the last sample above the
silence threshold* for each watched input. If that time is older than the configured window, you get
an alert: a macOS notification, a sound and optionally speech. Because it tracks timestamps, not the
last reported level, an input that stops reporting altogether is caught by the same rule
(reported as "stopped sending audio").

Optionally it can also try to heal the problem by hiding and re-showing the source in its scenes,
which makes OBS re-activate it without restarting OBS or the recording.

Safeguards against false alarms: nothing is checked while OBS is not recording (or paused), muted
inputs are ignored, and silence must last for the whole window (default 3 minutes).

## Status

| Part | State |
|---|---|
| Core watchdog (detector, alerts, OBS client, self-healing) | implemented, covered by tests |
| Command line (`obs-keeper run`, `inputs`, `test-alert`, `set-password`) | implemented |
| PySide6 settings UI with menu-bar icon (English/Russian) | planned |
| Not yet verified against a real occurrence of the bug | self-healing in particular is experimental |

## Requirements

- macOS (alerts use `osascript`, `afplay`, `say`), Python 3.10+
- OBS Studio 28+ (WebSocket server is built in)

## Setup

1. In OBS open **Tools → WebSocket Server Settings**, tick **Enable WebSocket server** and set a
   password (keep the default port 4455).
2. Install:

   ```shell
   python3 -m venv venv && source venv/bin/activate
   pip install -e .
   ```

3. Store the password in the macOS keychain (it is never written to the config file):

   ```shell
   obs-keeper set-password
   ```

   Alternatively export `OBS_KEEPER_PASSWORD`; it takes precedence over the keychain.
4. Look at what OBS exposes, and check that alerts reach you:

   ```shell
   obs-keeper inputs
   obs-keeper test-alert
   ```

5. Start watching (leave it running while you record):

   ```shell
   obs-keeper run
   ```

## Configuration

Settings live in a JSON file; `obs-keeper config-path` prints its location
(`~/Library/Application Support/obs-keeper/config.json`). Override it with `--config PATH` or
`OBS_KEEPER_CONFIG`. Missing keys fall back to defaults; unknown keys are ignored.

| Key | Default | Meaning |
|---|---|---|
| `obs.host`, `obs.port` | `localhost`, `4455` | Where the OBS WebSocket server listens |
| `monitor.inputs` | `[]` | Input names to watch; empty = every input that reports levels |
| `monitor.silence_threshold_db` | `-70` | Peak level at or below this counts as silence |
| `monitor.silence_seconds` | `180` | How long silence must last before alerting |
| `monitor.only_while_recording` | `true` | Watch only during a recording (`false` = whenever connected) |
| `monitor.include_streaming` | `false` | Also watch while streaming |
| `monitor.ignore_muted` | `true` | Never alert for inputs muted in OBS |
| `alerts.notification` / `sound` / `speech` | `true` / `true` / `false` | Alert channels |
| `alerts.sound_name` | `Sosumi` | Any name from `/System/Library/Sounds` |
| `alerts.speech_voice` | `""` | Voice for `say`; empty = system default |
| `alerts.repeat_seconds` | `120` | Repeat the alert this often while audio is still missing |
| `alerts.notify_recovery` | `true` | Quiet notification when sound returns |
| `remediation.enabled` | `false` | Try to restart the silent source automatically |
| `remediation.after_seconds` | `30` | Wait this long after the alert before the first attempt |
| `remediation.max_attempts` | `2` | Attempts per outage |
| `remediation.cooldown_seconds` | `300` | Minimum time between attempts |
| `language` | `auto` | `auto`, `en` or `ru` (alerts and, later, the UI) |

Self-healing only works for inputs that are items of a scene (e.g. **macOS Screen Capture**), not for
global audio devices.

## Recommendation: record audio twice

A watchdog tells you about a failure; redundancy survives it. Consider adding a second, independent
audio path (for example [BlackHole](https://github.com/ExistentialAudio/BlackHole) as an *Audio
Input Capture* source) and recording it to a separate track in OBS's Advanced output mode. Watch
both inputs with `obs-keeper`.

## Development

```shell
pip install -e ".[dev]"
python -m pytest
```

Tests need neither OBS nor a sound card: OBS is replaced by a small fake obs-websocket server
(`tests/fake_obs.py`), alert commands are captured instead of run. See [CLAUDE.md](CLAUDE.md) for
the layout and the rules for contributors.

## License

MIT, see [LICENSE](LICENSE).
