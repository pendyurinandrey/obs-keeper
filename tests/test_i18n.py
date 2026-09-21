import pytest

from obs_keeper import i18n
from obs_keeper.i18n import STRINGS, format_duration, resolve_language, tr


def test_both_languages_define_the_same_keys():
    assert set(STRINGS["en"]) == set(STRINGS["ru"])


def test_placeholders_match_between_languages():
    import string

    def fields(text):
        return {f for _, f, _, _ in string.Formatter().parse(text) if f}

    for key in STRINGS["en"]:
        assert fields(STRINGS["en"][key]) == fields(STRINGS["ru"][key]), key


def test_unknown_language_falls_back_to_english():
    assert tr("alert.lost.title", "de") == STRINGS["en"]["alert.lost.title"]


@pytest.mark.parametrize("seconds,en,ru", [
    (5, "5 s", "5 с"),
    (59.6, "1 min 00 s", "1 мин 00 с"),
    (185, "3 min 05 s", "3 мин 05 с"),
    (3725, "1 h 02 min", "1 ч 02 мин"),
])
def test_format_duration(seconds, en, ru):
    assert format_duration(seconds, "en") == en
    assert format_duration(seconds, "ru") == ru


def test_resolve_language_explicit_wins(monkeypatch):
    monkeypatch.setenv("LANG", "ru_RU.UTF-8")
    assert resolve_language("en") == "en"
    assert resolve_language("ru") == "ru"


def test_resolve_language_auto_reads_environment(monkeypatch):
    for var in ("LC_ALL", "LC_MESSAGES"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("LANG", "ru_RU.UTF-8")
    assert resolve_language("auto") == "ru"
    monkeypatch.setenv("LANG", "en_US.UTF-8")
    assert resolve_language("auto") == "en"
    assert i18n.system_language() == "en"
