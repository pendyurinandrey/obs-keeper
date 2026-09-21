"""Minimal obs-websocket v5 server for tests (handshake with password, a few requests, pushed events)."""

import base64
import hashlib
import json
import threading

from websockets.sync.server import serve

SALT, CHALLENGE = "test-salt", "test-challenge"


def expected_auth(password: str) -> str:
    secret = base64.b64encode(hashlib.sha256((password + SALT).encode()).digest())
    return base64.b64encode(hashlib.sha256(secret + CHALLENGE.encode()).digest()).decode()


class FakeObs:
    def __init__(self, password="secret", recording=False, inputs=None, muted=()):
        self.password = password
        self.recording = recording
        self.inputs = inputs or [("Desktop Audio", "screen_capture"), ("Mic", "coreaudio_input_capture")]
        self.muted = set(muted)
        self.scene_items = {"Scene": [{"sceneItemId": 1, "sourceName": "Desktop Audio", "sceneItemEnabled": True}]}
        self.requests: list[tuple[str, dict]] = []
        self._clients = []
        self.subs_seen: list[int] = []
        self._lock = threading.Lock()
        self._server = serve(self._handle, "127.0.0.1", 0, close_timeout=0.5)
        self.port = self._server.socket.getsockname()[1]
        threading.Thread(target=self._server.serve_forever, daemon=True).start()

    def close(self):
        self._server.shutdown()

    def push_event(self, event_type: str, data: dict, intent: int = 0):
        message = json.dumps({"op": 5, "d": {"eventType": event_type, "eventIntent": intent, "eventData": data}})
        with self._lock:
            for ws in list(self._clients):
                try:
                    ws.send(message)
                except Exception:  # noqa: BLE001
                    pass

    def _handle(self, ws):
        ws.send(json.dumps({"op": 0, "d": {
            "obsWebSocketVersion": "5.7.4", "rpcVersion": 1,
            "authentication": {"challenge": CHALLENGE, "salt": SALT},
        }}))
        identify = json.loads(ws.recv())
        if identify["d"].get("authentication") != expected_auth(self.password):
            ws.close(4009, "Authentication failed.")
            return
        ws.send(json.dumps({"op": 2, "d": {"negotiatedRpcVersion": 1}}))
        self.subs_seen.append(identify["d"].get("eventSubscriptions", 0))
        with self._lock:
            self._clients.append(ws)
        try:
            for raw in ws:
                message = json.loads(raw)
                if message["op"] != 6:
                    continue
                data = message["d"]
                self.requests.append((data["requestType"], data.get("requestData", {})))
                ws.send(json.dumps({"op": 7, "d": {
                    "requestType": data["requestType"], "requestId": data["requestId"],
                    "requestStatus": {"result": True, "code": 100},
                    "responseData": self._respond(data["requestType"], data.get("requestData", {})),
                }}))
        except Exception:  # noqa: BLE001 - client went away
            pass
        finally:
            with self._lock:
                if ws in self._clients:
                    self._clients.remove(ws)

    def _respond(self, kind, req):
        if kind == "GetVersion":
            return {"obsVersion": "32.2.2"}
        if kind == "GetRecordStatus":
            return {"outputActive": self.recording, "outputPaused": False}
        if kind == "GetStreamStatus":
            return {"outputActive": False}
        if kind == "GetInputList":
            return {"inputs": [{"inputName": n, "inputKind": k} for n, k in self.inputs]}
        if kind == "GetInputMute":
            return {"inputMuted": req["inputName"] in self.muted}
        if kind == "GetSceneList":
            return {"scenes": [{"sceneName": s, "sceneIndex": i} for i, s in enumerate(self.scene_items)]}
        if kind == "GetSceneItemList":
            return {"sceneItems": self.scene_items[req["sceneName"]]}
        if kind == "SetSceneItemEnabled":
            for item in self.scene_items[req["sceneName"]]:
                if item["sceneItemId"] == req["sceneItemId"]:
                    item["sceneItemEnabled"] = req["sceneItemEnabled"]
            return {}
        return {}
