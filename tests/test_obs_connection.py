"""ObsConnection against a fake obs-websocket server: real obsws-python, real sockets."""

import time

import pytest

from obs_keeper.obs_client import ObsConnection, ObsError
from tests.fake_obs import FakeObs


class Sink:
    def __init__(self):
        self.calls = []

    def meters(self, levels): self.calls.append(("meters", levels))
    def record_state(self, active): self.calls.append(("record", active))
    def stream_state(self, active): self.calls.append(("stream", active))
    def mute(self, name, muted): self.calls.append(("mute", name, muted))
    def obs_exiting(self): self.calls.append(("exit",))

    def wait_for(self, kind, timeout=3):
        deadline = time.time() + timeout
        while time.time() < deadline:
            hits = [c for c in self.calls if c[0] == kind]
            if hits:
                return hits[-1]
            time.sleep(0.02)
        raise AssertionError(f"no {kind} event; got {self.calls}")


@pytest.fixture
def obs():
    server = FakeObs(password="secret", recording=True, muted={"Mic"})
    yield server
    server.close()


@pytest.fixture
def conn(obs):
    sink = Sink()
    connection = ObsConnection.connect("127.0.0.1", obs.port, "secret", sink)
    connection.sink = sink
    yield connection
    connection.close()


def test_requests(conn):
    assert conn.alive()
    conn.ping()
    assert conn.recording_active() is True
    assert conn.streaming_active() is False
    assert conn.list_inputs() == [("Desktop Audio", "screen_capture"), ("Mic", "coreaudio_input_capture")]
    assert conn.muted_inputs() == {"Mic"}


def test_events_reach_the_sink(conn, obs):
    obs.push_event("InputVolumeMeters", {"inputs": [
        {"inputName": "Desktop Audio", "inputUuid": "u", "inputLevelsMul": [[0.5, 0.1, 0.1]]},
    ]}, intent=1 << 16)
    _, levels = conn.sink.wait_for("meters")
    assert levels[0][0] == "Desktop Audio" and abs(levels[0][1] + 20) < 1e-6

    obs.push_event("RecordStateChanged", {"outputActive": False, "outputState": "OBS_WEBSOCKET_OUTPUT_STOPPED"})
    assert conn.sink.wait_for("record") == ("record", False)

    obs.push_event("InputMuteStateChanged", {"inputName": "Mic", "inputUuid": "u", "inputMuted": False})
    assert conn.sink.wait_for("mute") == ("mute", "Mic", False)


def test_volume_meters_are_actually_subscribed(conn, obs):
    conn.ping()
    time.sleep(0.2)
    # the connection that listens for events must have asked for the high-volume meters (1 << 16)
    from obsws_python.subs import Subs
    assert any(subs & Subs.INPUTVOLUMEMETERS for subs in obs.subs_seen)


def test_restart_source_toggles_scene_item_off_and_on(conn, obs):
    assert conn.restart_source("Desktop Audio", pause=0.05) == 1
    toggles = [(t, d["sceneItemEnabled"]) for t, d in obs.requests if t == "SetSceneItemEnabled"]
    assert toggles == [("SetSceneItemEnabled", False), ("SetSceneItemEnabled", True)]
    assert obs.scene_items["Scene"][0]["sceneItemEnabled"] is True


def test_restart_source_not_in_any_scene_is_a_noop(conn, obs):
    assert conn.restart_source("Mic", pause=0.01) == 0
    assert not [t for t, _ in obs.requests if t == "SetSceneItemEnabled"]


def test_wrong_password_is_reported_as_auth_error(obs):
    with pytest.raises(ObsError) as info:
        ObsConnection.connect("127.0.0.1", obs.port, "wrong", Sink())
    assert info.value.kind == "auth"


def test_missing_password_is_reported_as_auth_error(obs):
    with pytest.raises(ObsError) as info:
        ObsConnection.connect("127.0.0.1", obs.port, "", Sink())
    assert info.value.kind == "auth"


def test_closed_port_is_reported_as_refused():
    server = FakeObs()
    port = server.port
    server.close()
    time.sleep(0.2)
    with pytest.raises(ObsError) as info:
        ObsConnection.connect("127.0.0.1", port, "secret", Sink())
    assert info.value.kind == "refused"


def test_dead_socket_is_noticed(conn, obs):
    obs.close()
    for ws in list(obs._clients):
        ws.close()
    deadline = time.time() + 3
    while time.time() < deadline and conn.alive():
        time.sleep(0.05)
    assert not conn.alive()
