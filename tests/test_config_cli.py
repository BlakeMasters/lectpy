import json
from pathlib import Path

import pytest

from lecture.cli import main
from lecture.config import ConfigError, load_project


def project(tmp_path, config, source='from lecture import text\ndef main():\n    text("Hello")\n'):
    (tmp_path / "lecture.toml").write_text(config, encoding="utf-8")
    (tmp_path / "lesson.py").write_text(source, encoding="utf-8")
    return tmp_path / "lecture.toml"


def test_nested_discovery_and_config_relative_entry(tmp_path, monkeypatch):
    project(tmp_path, '[lecture]\nentry="lesson.py"\ntitle="A configured title"\n')
    nested = tmp_path / "chapters"
    nested.mkdir()
    monkeypatch.chdir(nested)
    assert load_project().root == tmp_path
    assert main(["build"]) == 0
    bundle = json.loads((tmp_path / "dist/lesson/lecture.json").read_text())
    assert bundle["manifest"]["title"] == "A configured title"
    assert bundle["manifest"]["policy_profile"] == "static"
    assert any(e["kind"] == "text" for e in bundle["events"])
    assert not (nested / ".lecture").exists()


def test_plain_python_document_and_explicit_overrides(tmp_path, monkeypatch):
    project(
        tmp_path,
        '[lecture]\nentry="lesson.py"\ntitle="Configured"\n[runtimes.python]\nprovider="python"\n',
    )
    monkeypatch.chdir(tmp_path)
    assert main(["build"]) == 0
    bundle = json.loads((tmp_path / "dist/lesson/lecture.json").read_text())
    assert bundle["manifest"]["runtime"] == "python"
    assert [e["kind"] for e in bundle["events"]] == ["session_start", "text", "session_end"]
    assert main(["build", "--provider", "trace", "--title", "Override"]) == 0
    bundle = json.loads((tmp_path / "dist/lesson/lecture.json").read_text())
    assert bundle["manifest"]["title"] == "Override"
    assert any(e["kind"] == "step" for e in bundle["events"])


def test_explicit_source_overrides_config_entry(tmp_path, monkeypatch):
    project(tmp_path, '[lecture]\nentry="missing.py"\n')
    monkeypatch.chdir(tmp_path)
    assert main(["trace", "lesson.py", "--out", "trace.json"]) == 0
    assert (tmp_path / "trace.json").is_file()


def test_policy_limits_and_relative_paths(tmp_path):
    path = project(
        tmp_path,
        '[policy.default]\nprofile="local-trusted"\nprocess="deny"\n'
        'max-events=500\nmax-wall-seconds=2.5\nfilesystem-read=["data"]\n',
    )
    config = load_project(config_path=str(path))
    policy = config.execution_policy()
    assert policy.max_events == 500
    assert policy.max_wall_seconds == 2.5
    assert policy.process == "deny"
    assert policy.fs_read == (str(tmp_path / "data"),)
    assert config.execution_policy("local-trusted").process == "allow"


@pytest.mark.parametrize(
    "config, message",
    [
        ("[lecture]\nformat-version=2", "format-version"),
        ("[lecture]\nformat-version=true", "format-version"),
        ("[lecture]\nentry=42", "entry"),
        ('[runtimes.python]\nprovider="jupyter"', "provider"),
        ('[runtimes.python]\nprovider=["trace"]', "provider"),
        ("[policy.default]\nmax-events=true", "max-events"),
        ("[policy.default]\nmax-wall-seconds=nan", "max-wall-seconds"),
        ("[policy.default]\nmax-events=1.5", "max-events"),
        ("[policy.default]\nmax-output-bytes=0", "max-output-bytes"),
        ('[policy.default]\nfilesystem-read="data"', "filesystem-read"),
        ('[policy.default]\nnetwork="maybe"', "network"),
        ('[policy.default]\nprofile="static"', "delivery profile"),
        ('[export.static]\ninteractive-fallback="live"', "interactive-fallback"),
        ('[lecture]\ntitel="typo"', "titel"),
        ("lecture = [1]", "TOML table"),
        ("[broken", "cannot read"),
    ],
)
def test_invalid_config_is_actionable(tmp_path, config, message):
    path = project(tmp_path, config)
    with pytest.raises(ConfigError, match=message):
        load_project(config_path=str(path))


def test_check_never_imports_or_executes_source(tmp_path, monkeypatch):
    project(tmp_path, '[lecture]\nentry="lesson.py"', 'raise RuntimeError("do not run")\n')
    monkeypatch.chdir(tmp_path)
    assert main(["check"]) == 0
    assert not (tmp_path / ".lecture").exists()
    assert not (tmp_path / "dist").exists()


def test_check_reports_syntax_error_and_missing_config(tmp_path, monkeypatch, capsys):
    project(tmp_path, '[lecture]\nentry="lesson.py"', "def invalid(:\n")
    monkeypatch.chdir(tmp_path)
    assert main(["check"]) == 2
    assert "lesson.py:1" in capsys.readouterr().err
    assert main(["check", "--config", "missing.toml"]) == 2
    assert "no such config" in capsys.readouterr().err


def test_failed_execution_retains_replay_but_exits_nonzero(tmp_path, monkeypatch):
    project(tmp_path, '[lecture]\nentry="lesson.py"', 'def main():\n    raise ValueError("boom")\n')
    monkeypatch.chdir(tmp_path)
    assert main(["build"]) == 1
    assert (tmp_path / "dist/lesson/index.html").is_file()
    assert main(["trace"]) == 1


def test_init_scaffolds_usable_project_without_overwriting(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert main(["init"]) == 0
    assert main(["check"]) == 0
    assert main(["build"]) == 0
    config_path = Path("lecture.toml")
    config_path.write_text('[lecture]\ntitle="Mine"', encoding="utf-8")
    assert main(["init"]) == 0
    assert config_path.read_text() == '[lecture]\ntitle="Mine"'


def test_static_execution_profile_is_rejected_before_running(tmp_path, monkeypatch, capsys):
    project(tmp_path, '[lecture]\nentry="lesson.py"')
    monkeypatch.chdir(tmp_path)
    assert main(["build", "--policy", "static"]) == 2
    assert "delivery profile" in capsys.readouterr().err
    assert not (tmp_path / ".lecture").exists()


def test_file_without_project_keeps_default_behavior(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    Path("lesson.py").write_text("def main():\n    x = 1\n", encoding="utf-8")
    assert load_project("lesson.py").path is None
    assert main(["build", "lesson.py"]) == 0
