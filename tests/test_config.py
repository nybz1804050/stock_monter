"""config 模块：默认值 / 文件 / 环境变量 / 显式覆盖的优先级。"""
import json

from stockmon import config


def test_defaults_when_nothing_provided():
    cfg = config.load()
    assert cfg["interval"] == 5.0 and cfg["port"] == 8000


def test_file_overrides_defaults_and_ignores_unknown_keys(tmp_path):
    (tmp_path / "config.json").write_text(
        json.dumps({"interval": 9, "port": 9001, "unknown": 1}), encoding="utf-8")
    cfg = config.load(str(tmp_path))
    assert cfg["interval"] == 9 and cfg["port"] == 9001
    assert "unknown" not in cfg


def test_env_overrides_file(tmp_path, monkeypatch):
    (tmp_path / "config.json").write_text(json.dumps({"interval": 9}), encoding="utf-8")
    monkeypatch.setenv("STOCKMON_INTERVAL", "2.5")
    monkeypatch.setenv("STOCKMON_PORT", "9100")
    cfg = config.load(str(tmp_path))
    assert cfg["interval"] == 2.5 and cfg["port"] == 9100


def test_explicit_overrides_win(tmp_path, monkeypatch):
    monkeypatch.setenv("STOCKMON_INTERVAL", "2.5")
    cfg = config.load(str(tmp_path), {"interval": 7.0})
    assert cfg["interval"] == 7.0


def test_bad_values_fall_back_to_default(monkeypatch):
    monkeypatch.setenv("STOCKMON_PORT", "not-a-number")
    assert config.load()["port"] == 8000
