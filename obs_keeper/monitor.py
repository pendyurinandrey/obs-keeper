"""Runs the watchdog: keeps a connection to OBS, feeds the detector, delivers alerts.

One worker thread owns the connection and does all requests to OBS. OBS events arrive on the
obsws-python event thread and only touch the detector (under ``_lock``).
"""

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from obs_keeper.alerts import AlertDispatcher
from obs_keeper.config import Config
from obs_keeper.detector import RECOVERED, REMEDIATE, InputSnapshot, SilenceDetector, Transition
from obs_keeper.i18n import resolve_language, tr
from obs_keeper.obs_client import ObsConnection, ObsError, ObsSink

log = logging.getLogger(__name__)

CONNECTING = "connecting"
CONNECTED = "connected"
DISCONNECTED = "disconnected"

HEARTBEAT_EVERY_TICKS = 5
RETRY_SECONDS = 5.0

ConnectFn = Callable[[str, int, str, ObsSink], ObsConnection]


@dataclass(frozen=True)
class Status:
    connection: str = DISCONNECTED
    error: str = ""  # human-readable, already translated
    recording: bool = False
    streaming: bool = False
    watching: bool = False  # the detector is armed (e.g. recording is on)
    alerting: bool = False  # at least one input is currently lost
    inputs: list[InputSnapshot] = field(default_factory=list)


class Monitor:
    def __init__(
        self,
        config: Config,
        password: Callable[[], str],
        connect: ConnectFn = ObsConnection.connect,
        dispatcher: AlertDispatcher | None = None,
        clock: Callable[[], float] = time.monotonic,
    ):
        self._config = config
        self._password = password
        self._connect = connect
        self._clock = clock
        self._language = resolve_language(config.language)
        self._alerts = dispatcher or AlertDispatcher(config.alerts, self._language)
        self._detector = SilenceDetector(config.monitor, config.alerts.repeat_seconds, config.remediation)
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._listeners: list[Callable[[Status], None]] = []
        self._conn: ObsConnection | None = None
        self._connection = DISCONNECTED
        self._error = ""
        self._recording = False
        self._streaming = False

    # -- public API ---------------------------------------------------------------------------

    def add_listener(self, listener: Callable[[Status], None]) -> None:
        """``listener(status)`` is called about once a second from the worker thread."""
        self._listeners.append(listener)

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="obs-keeper-monitor", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=10)

    def apply_config(self, config: Config) -> None:
        """Apply new settings on the fly. Host/port/password changes take effect on reconnect."""
        with self._lock:
            reconnect = config.obs != self._config.obs
            self._config = config
            self._language = resolve_language(config.language)
            self._alerts.config = config.alerts
            self._alerts.language = self._language
            self._detector.configure(
                config.monitor, config.alerts.repeat_seconds, config.remediation, self._clock()
            )
            self._refresh_active()
        if reconnect and self._conn:
            self._conn.close()  # the worker notices and reconnects with the new settings

    def send_test_alert(self) -> None:
        self._alerts.send_test()

    def status(self) -> Status:
        with self._lock:
            now = self._clock()
            return Status(
                connection=self._connection,
                error=self._error,
                recording=self._recording,
                streaming=self._streaming,
                watching=self._detector.active,
                alerting=self._detector.any_lost(),
                inputs=self._detector.snapshot(now),
            )

    def list_inputs(self) -> list[tuple[str, str]]:
        """Inputs known to OBS right now (empty when not connected)."""
        conn = self._conn
        if conn is None:
            return []
        try:
            return conn.list_inputs()
        except Exception:  # noqa: BLE001 - the connection may die at any moment
            return []

    # -- worker -------------------------------------------------------------------------------

    def _run(self) -> None:
        while not self._stop.is_set():
            conn = self._try_connect()
            if conn is None:
                self._notify()
                self._stop.wait(RETRY_SECONDS)
                continue
            try:
                self._serve(conn)
            except Exception as e:  # noqa: BLE001 - whatever went wrong, reconnect instead of dying
                detail = e.detail if isinstance(e, ObsError) and e.detail else str(e)
                log.warning("Lost connection to OBS: %s", detail)
                self._set_connection(DISCONNECTED, tr("conn.error.other", self._language, detail=detail))
            finally:
                self._conn = None
                conn.close()
                with self._lock:
                    self._recording = self._streaming = False
                    self._detector.set_active(False, self._clock())
                self._notify()
        self._set_connection(DISCONNECTED, "")

    def _try_connect(self) -> ObsConnection | None:
        self._set_connection(CONNECTING, "")
        self._notify()
        cfg = self._config.obs
        try:
            conn = self._connect(cfg.host, cfg.port, self._password(), _Sink(self))
        except ObsError as e:
            key = {"refused": "conn.error.refused", "auth": "conn.error.auth"}.get(e.kind, "conn.error.other")
            message = tr(key, self._language, detail=e.detail)
            log.info("OBS not reachable: %s", message)
            self._set_connection(DISCONNECTED, message)
            return None
        return conn

    def _serve(self, conn: ObsConnection) -> None:
        now = self._clock()
        recording, streaming, muted = conn.recording_active(), conn.streaming_active(), conn.muted_inputs()
        self._conn = conn
        with self._lock:
            self._recording, self._streaming = recording, streaming
            for name in muted:
                self._detector.set_muted(name, True, now)
            self._refresh_active()
        self._set_connection(CONNECTED, "")
        log.info("Connected to OBS (recording=%s, streaming=%s)", self._recording, self._streaming)
        ticks = 0
        while not self._stop.wait(1.0):
            ticks += 1
            if not conn.alive():
                raise ObsError("other", "connection closed")
            if ticks % HEARTBEAT_EVERY_TICKS == 0:
                conn.ping()
            self.tick(conn)
            self._notify()

    def tick(self, conn: ObsConnection | None = None) -> None:
        """Advance detector timers, deliver alerts, run self-healing. Called once a second."""
        with self._lock:
            transitions = self._detector.evaluate(self._clock())
            max_attempts = self._config.remediation.max_attempts
        for transition in transitions:
            self._deliver(transition, max_attempts)
            if transition.kind == REMEDIATE and conn is not None:
                self._remediate(conn, transition)

    # -- events from OBS (event thread) -------------------------------------------------------

    def _on_meters(self, levels: list[tuple[str, float]]) -> None:
        now = self._clock()
        transitions: list[Transition] = []
        with self._lock:
            for name, db in levels:
                transitions += self._detector.on_sample(name, db, now)
        for transition in transitions:
            self._deliver(transition, 0)

    def _on_record_state(self, active: bool) -> None:
        with self._lock:
            self._recording = active
            self._refresh_active()

    def _on_stream_state(self, active: bool) -> None:
        with self._lock:
            self._streaming = active
            self._refresh_active()

    def _on_mute(self, name: str, muted: bool) -> None:
        with self._lock:
            self._detector.set_muted(name, muted, self._clock())

    # -- helpers ------------------------------------------------------------------------------

    def _refresh_active(self) -> None:
        """Caller holds ``_lock``."""
        cfg = self._config.monitor
        if cfg.only_while_recording:
            active = self._recording or (cfg.include_streaming and self._streaming)
        else:
            active = self._conn is not None
        if active != self._detector.active:
            log.info("Watching audio: %s", "on" if active else "off")
        self._detector.set_active(active, self._clock())

    def _deliver(self, transition: Transition, max_attempts: int) -> None:
        level = logging.INFO if transition.kind == RECOVERED else logging.WARNING
        log.log(level, "%s: input %r (%.0f s, %s)", transition.kind, transition.input_name,
                transition.silent_for, transition.reason)
        self._alerts.handle(transition, max_attempts)

    def _remediate(self, conn: ObsConnection, transition: Transition) -> None:
        try:
            toggled = conn.restart_source(transition.input_name)
        except Exception as e:  # noqa: BLE001 - a failed heal must never take the watchdog down
            log.error("Restarting %r failed: %s", transition.input_name, e)
            return
        if toggled:
            log.info("Restarted %r (%d scene item(s))", transition.input_name, toggled)
        else:
            log.warning("Cannot restart %r: it is not an item of any scene", transition.input_name)

    def _set_connection(self, state: str, error: str) -> None:
        with self._lock:
            self._connection = state
            self._error = error

    def _notify(self) -> None:
        if not self._listeners:
            return
        status = self.status()
        for listener in self._listeners:
            try:
                listener(status)
            except Exception:  # noqa: BLE001 - a broken UI callback must not stop the watchdog
                log.exception("Status listener failed")


class _Sink:
    """Adapter: ``ObsSink`` calls from the event thread into the monitor."""

    def __init__(self, monitor: Monitor):
        self._monitor = monitor

    def meters(self, levels: list[tuple[str, float]]) -> None:
        self._monitor._on_meters(levels)

    def record_state(self, active: bool) -> None:
        self._monitor._on_record_state(active)

    def stream_state(self, active: bool) -> None:
        self._monitor._on_stream_state(active)

    def mute(self, input_name: str, muted: bool) -> None:
        self._monitor._on_mute(input_name, muted)

    def obs_exiting(self) -> None:
        log.info("OBS is exiting")
