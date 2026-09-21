"""Command line: run the watchdog headless, list OBS inputs, test alerts, store the password."""

import argparse
import getpass
import logging
import sys
import time
from pathlib import Path

from obs_keeper import __version__
from obs_keeper.alerts import AlertDispatcher
from obs_keeper.config import Config, config_path, load_config
from obs_keeper.credentials import get_password, set_password
from obs_keeper.i18n import resolve_language, tr
from obs_keeper.monitor import Monitor
from obs_keeper.obs_client import ObsConnection, ObsError


class _NullSink:
    def meters(self, levels): ...
    def record_state(self, active): ...
    def stream_state(self, active): ...
    def mute(self, input_name, muted): ...
    def obs_exiting(self): ...


def _load(args: argparse.Namespace) -> tuple[Config, str]:
    config = load_config(Path(args.config) if args.config else None)
    language = resolve_language(config.language)
    problems = config.validate()
    if problems:
        print(tr("cli.config_problems", language), *problems, sep="\n  ", file=sys.stderr)
        raise SystemExit(2)
    return config, language


def cmd_run(args: argparse.Namespace) -> int:
    config, language = _load(args)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if not get_password():
        logging.warning(tr("cli.no_password", language))
    monitor = Monitor(config, get_password)
    monitor.start()
    print(tr("cli.watching", language), file=sys.stderr)
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        pass
    finally:
        monitor.stop()
    return 0


def cmd_inputs(args: argparse.Namespace) -> int:
    config, language = _load(args)
    try:
        conn = ObsConnection.connect(config.obs.host, config.obs.port, get_password(), _NullSink())
    except ObsError as e:
        key = {"refused": "conn.error.refused", "auth": "conn.error.auth"}.get(e.kind, "conn.error.other")
        print(tr(key, language, detail=e.detail), file=sys.stderr)
        return 1
    try:
        for name, kind in conn.list_inputs():
            print(f"{name}\t{kind}")
    finally:
        conn.close()
    return 0


def cmd_test_alert(args: argparse.Namespace) -> int:
    config, language = _load(args)
    AlertDispatcher(config.alerts, language).send_test()
    time.sleep(3)  # alerts run in daemon threads; give them a moment before the process exits
    return 0


def cmd_set_password(args: argparse.Namespace) -> int:
    _config, language = _load(args)
    set_password(getpass.getpass(tr("cli.password_prompt", language)))
    print(tr("cli.password_saved", language))
    return 0


def cmd_config_path(args: argparse.Namespace) -> int:
    print(Path(args.config) if args.config else config_path())
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="obs-keeper", description="Watchdog that alerts when OBS audio goes silent.")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--config", help="path to config.json (default: see `config-path`)")
    sub = parser.add_subparsers(dest="command")
    for name, func, help_text in (
        ("run", cmd_run, "watch OBS without a UI"),
        ("inputs", cmd_inputs, "list OBS inputs (name<TAB>kind)"),
        ("test-alert", cmd_test_alert, "send a test alert through the configured channels"),
        ("set-password", cmd_set_password, "store the OBS WebSocket password in the system keychain"),
        ("config-path", cmd_config_path, "print where the config file lives"),
    ):
        sub.add_parser(name, help=help_text).set_defaults(func=func)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 2
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
