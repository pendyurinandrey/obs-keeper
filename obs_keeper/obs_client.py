"""Thin wrapper over ``obsws-python``: connection, event fan-out, the few requests we need.

Everything above this module talks to ``ObsConnection`` and ``ObsSink`` only, so tests can replace
OBS with a fake.
"""

import logging
import time
from typing import Protocol

import obsws_python as obsws
from obsws_python.error import OBSSDKError
from obsws_python.subs import Subs
from websocket import WebSocketConnectionClosedException

from obs_keeper.levels import peak_db

# SECURITY: obsws-python logs "password='...'" in clear text at INFO level. Keep it at WARNING+.
logging.getLogger("obsws_python").setLevel(logging.WARNING)

log = logging.getLogger(__name__)

CONNECT_TIMEOUT_SECONDS = 5
_RECORDING_STATES = ("OBS_WEBSOCKET_OUTPUT_STARTED", "OBS_WEBSOCKET_OUTPUT_RESUMED")


class ObsError(Exception):
    """``kind`` is ``refused`` (server off/OBS closed), ``auth`` or ``other``."""

    def __init__(self, kind: str, detail: str = ""):
        super().__init__(f"{kind}: {detail}" if detail else kind)
        self.kind = kind
        self.detail = detail


class ObsSink(Protocol):
    """What the monitor wants to hear from OBS. Called from the event thread."""

    def meters(self, levels: list[tuple[str, float]]) -> None: ...
    def record_state(self, active: bool) -> None: ...
    def stream_state(self, active: bool) -> None: ...
    def mute(self, input_name: str, muted: bool) -> None: ...
    def obs_exiting(self) -> None: ...


class _Events:
    """Handlers named exactly ``on_<snake_case_event>``: obsws-python dispatches by ``__name__``."""

    HANDLERS = (
        "on_input_volume_meters",
        "on_record_state_changed",
        "on_stream_state_changed",
        "on_input_mute_state_changed",
        "on_exit_started",
    )

    def __init__(self, sink: ObsSink):
        self._sink = sink

    def on_input_volume_meters(self, data) -> None:
        self._sink.meters([(i["inputName"], peak_db(i["inputLevelsMul"])) for i in data.inputs])

    def on_record_state_changed(self, data) -> None:
        self._sink.record_state(data.output_state in _RECORDING_STATES)

    def on_stream_state_changed(self, data) -> None:
        self._sink.stream_state(data.output_active)

    def on_input_mute_state_changed(self, data) -> None:
        self._sink.mute(data.input_name, data.input_muted)

    def on_exit_started(self, data) -> None:
        self._sink.obs_exiting()


class ObsConnection:
    def __init__(self, req: obsws.ReqClient, events: obsws.EventClient):
        self._req = req
        self._events = events

    @classmethod
    def connect(cls, host: str, port: int, password: str, sink: ObsSink) -> "ObsConnection":
        req = events = None
        try:
            req = obsws.ReqClient(host=host, port=port, password=password, timeout=CONNECT_TIMEOUT_SECONDS)
            events = obsws.EventClient(
                host=host, port=port, password=password, subs=Subs.LOW_VOLUME | Subs.INPUTVOLUMEMETERS
            )
            handlers = _Events(sink)
            events.callback.register([getattr(handlers, name) for name in _Events.HANDLERS])
        except ConnectionRefusedError as e:
            raise ObsError("refused", str(e)) from e
        except WebSocketConnectionClosedException as e:  # OBS closes the socket on a wrong password
            raise ObsError("auth", str(e)) from e
        except OBSSDKError as e:
            # A wrong password makes OBS close the socket during Identify, which obsws-python
            # reports as "failed to identify client"; no password at all as "authentication enabled".
            auth = "failed to identify" in str(e) or "authentication" in str(e)
            raise ObsError("auth" if auth else "other", str(e)) from e
        except (OSError, ValueError) as e:
            raise ObsError("other", str(e)) from e
        finally:
            failed = events is None or req is None
            if failed:
                for client in (req, events):
                    if client is not None:
                        try:
                            client.disconnect()
                        except Exception:  # noqa: BLE001 - best-effort cleanup of a half-open connection
                            pass
        return cls(req, events)

    def close(self) -> None:
        for client in (self._events, self._req):
            try:
                client.disconnect()
            except Exception:  # noqa: BLE001 - already closed sockets raise assorted errors
                pass

    def alive(self) -> bool:
        """The event thread of obsws-python ends silently when the socket dies."""
        return self._events.worker.is_alive()

    def ping(self) -> None:
        try:
            self._req.get_version()
        except Exception as e:  # noqa: BLE001
            raise ObsError("other", f"heartbeat failed: {e}") from e

    def recording_active(self) -> bool:
        status = self._req.get_record_status()
        return bool(status.output_active and not status.output_paused)

    def streaming_active(self) -> bool:
        return bool(self._req.get_stream_status().output_active)

    def list_inputs(self) -> list[tuple[str, str]]:
        """``(name, kind)`` of every input."""
        return [(i["inputName"], i["inputKind"]) for i in self._req.get_input_list().inputs]

    def muted_inputs(self) -> set[str]:
        muted = set()
        for name, _kind in self.list_inputs():
            try:
                if self._req.get_input_mute(name).input_muted:
                    muted.add(name)
            except OBSSDKError:
                continue  # input without audio
        return muted

    def restart_source(self, input_name: str, pause: float = 1.0) -> int:
        """Hide and re-show every scene item of the input, making OBS re-activate the source.

        Returns how many scene items were toggled; 0 means the input is not in any scene
        (e.g. a global audio device), so there was nothing to restart.
        """
        items = []
        for scene in self._req.get_scene_list().scenes:
            scene_name = scene["sceneName"]
            for item in self._req.get_scene_item_list(scene_name).scene_items:
                if item["sourceName"] == input_name and item["sceneItemEnabled"]:
                    items.append((scene_name, item["sceneItemId"]))
        for scene_name, item_id in items:
            self._req.set_scene_item_enabled(scene_name, item_id, False)
        time.sleep(pause)
        for scene_name, item_id in items:
            self._req.set_scene_item_enabled(scene_name, item_id, True)
        return len(items)
