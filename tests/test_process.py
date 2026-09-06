import pytest

from lecture.policy import PolicyViolation, default_policy
from lecture.providers.process import run_one_shot


def test_one_shot_python_version():
    p = default_policy("local-trusted")
    r = run_one_shot(["python", "--version"], policy=p)
    assert r.exit_code == 0
    assert "Python" in r.output


def test_policy_denies_in_static():
    p = default_policy("static")
    with pytest.raises(PolicyViolation):
        run_one_shot(["python", "--version"], policy=p)


def test_blocked_env_rejected():
    p = default_policy("local-trusted")
    with pytest.raises(PolicyViolation):
        run_one_shot(["python", "--version"], policy=p, env={"LD_PRELOAD": "/tmp/x.so"})


def test_output_truncated_with_notice():
    p = default_policy("local-trusted")
    p = type(p)(**{**p.__dict__, "max_output_bytes": 100})
    r = run_one_shot(["python", "-c", "print('A'*10000)"], policy=p)
    assert r.truncated_bytes > 0
    assert "truncated" in r.output
    assert len(r.output.encode("utf-8")) < 10000


def test_missing_binary_reports_127():
    p = default_policy("local-trusted")
    r = run_one_shot(["lectpy-definitely-missing-binary-xyz"], policy=p)
    assert r.exit_code == 127
