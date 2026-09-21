import json

from obs_keeper.config import Config, config_from_dict, config_path, load_config, save_config


def test_roundtrip(tmp_path):
    config = Config()
    config.monitor.inputs = ["Desktop Audio", "Mic"]
    config.monitor.silence_threshold_db = -55.5
    config.alerts.speech = True
    config.remediation.enabled = True
    config.language = "ru"
    path = save_config(config, tmp_path / "sub" / "config.json")
    assert load_config(path) == config


def test_missing_and_corrupt_files_give_defaults(tmp_path):
    assert load_config(tmp_path / "nope.json") == Config()
    bad = tmp_path / "bad.json"
    bad.write_text("{not json")
    assert load_config(bad) == Config()


def test_unknown_keys_and_wrong_types_are_ignored():
    config = config_from_dict({
        "monitor": {"silence_seconds": "soon", "unknown": 1, "inputs": ["ok", 3], "ignore_muted": False},
        "alerts": "garbage",
        "language": 5,
        "obs": {"port": True},
    })
    defaults = Config()
    assert config.monitor.silence_seconds == defaults.monitor.silence_seconds
    assert config.monitor.inputs == []  # a list with a non-string is rejected as a whole
    assert config.monitor.ignore_muted is False
    assert config.alerts == defaults.alerts
    assert config.language == "auto"
    assert config.obs.port == 4455  # bool is not an int here


def test_int_is_accepted_for_float_fields():
    assert config_from_dict({"monitor": {"silence_threshold_db": -60}}).monitor.silence_threshold_db == -60.0


def test_validate_defaults_are_valid_and_bad_values_reported():
    assert Config().validate() == []
    config = Config()
    config.obs.port = 0
    config.monitor.silence_seconds = 1
    config.monitor.warn_seconds = 0
    config.monitor.silence_threshold_db = 5
    config.alerts.sound_seconds = 0
    config.alerts.repeat_seconds = 1
    config.language = "de"
    assert len(config.validate()) == 7


def test_config_path_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv("OBS_KEEPER_CONFIG", str(tmp_path / "x.json"))
    assert config_path() == tmp_path / "x.json"


def test_saved_file_is_readable_json_with_unicode(tmp_path):
    config = Config()
    config.monitor.inputs = ["Микрофон"]
    path = save_config(config, tmp_path / "c.json")
    assert "Микрофон" in path.read_text(encoding="utf-8")
    assert json.loads(path.read_text(encoding="utf-8"))["monitor"]["inputs"] == ["Микрофон"]
