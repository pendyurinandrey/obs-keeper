"""OBS WebSocket password: environment variable first, then the system keychain."""

import os

import keyring
from keyring.errors import KeyringError

PASSWORD_ENV = "OBS_KEEPER_PASSWORD"
_SERVICE = "obs-keeper"
_ACCOUNT = "obs-websocket"


def get_password() -> str:
    env = os.environ.get(PASSWORD_ENV)
    if env is not None:
        return env
    try:
        return keyring.get_password(_SERVICE, _ACCOUNT) or ""
    except KeyringError:
        return ""


def set_password(password: str) -> None:
    keyring.set_password(_SERVICE, _ACCOUNT, password)
