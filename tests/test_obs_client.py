import logging
from types import SimpleNamespace

from obs_keeper.obs_client import _Events


class Sink:
    def __init__(self):
        self.calls = []

    def meters(self, levels): self.calls.append(("meters", levels))
    def record_state(self, active): self.calls.append(("record", active))
    def stream_state(self, active): self.calls.append(("stream", active))
    def mute(self, name, muted): self.calls.append(("mute", name, muted))
    def obs_exiting(self): self.calls.append(("exit",))


def test_handler_names_match_obsws_dispatch_convention():
    # obsws-python calls fn when fn.__name__ == "on_" + snake_case(event type)
    from obsws_python.util import to_snake_case

    events = ["InputVolumeMeters", "RecordStateChanged", "StreamStateChanged", "InputMuteStateChanged", "ExitStarted"]
    assert sorted(f"on_{to_snake_case(e)}" for e in events) == sorted(_Events.HANDLERS)
    handlers = _Events(Sink())
    assert all(getattr(handlers, name).__name__ == name for name in _Events.HANDLERS)


def test_meters_are_converted_to_db_peaks():
    sink = Sink()
    data = SimpleNamespace(inputs=[
        {"inputName": "Desktop", "inputLevelsMul": [[0.5, 0.1, 0.1], [0.5, 0.05, 0.1]]},
        {"inputName": "Mic", "inputLevelsMul": [[0, 0, 0]]},
    ])
    _Events(sink).on_input_volume_meters(data)
    (_, levels), = sink.calls
    assert levels[0][0] == "Desktop" and abs(levels[0][1] + 20.0) < 1e-6
    assert levels[1][0] == "Mic" and levels[1][1] <= -120.0


def test_record_state_counts_pause_as_not_recording():
    sink = Sink()
    handlers = _Events(sink)
    for state in ("OBS_WEBSOCKET_OUTPUT_STARTED", "OBS_WEBSOCKET_OUTPUT_PAUSED",
                  "OBS_WEBSOCKET_OUTPUT_RESUMED", "OBS_WEBSOCKET_OUTPUT_STOPPING", "OBS_WEBSOCKET_OUTPUT_STOPPED"):
        handlers.on_record_state_changed(SimpleNamespace(output_state=state))
    assert [c[1] for c in sink.calls] == [True, False, True, False, False]


def test_mute_and_stream_events():
    sink = Sink()
    handlers = _Events(sink)
    handlers.on_input_mute_state_changed(SimpleNamespace(input_name="Mic", input_muted=True))
    handlers.on_stream_state_changed(SimpleNamespace(output_active=True))
    assert sink.calls == [("mute", "Mic", True), ("stream", True)]


def test_password_never_reaches_info_logs():
    # obsws-python logs "password='...'" at INFO; obs_keeper must keep that logger above INFO.
    assert logging.getLogger("obsws_python").getEffectiveLevel() >= logging.WARNING
    assert not logging.getLogger("obsws_python.baseclient.ObsClient").isEnabledFor(logging.INFO)
