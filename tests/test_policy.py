import pytest

from lecture.policy import (
    GrantedPolicy,
    PolicyViolation,
    check_fs_read,
    check_network,
    check_process,
    default_policy,
)


def test_all_profiles_construct():
    for profile in ("static", "local-trusted", "local-restricted", "classroom", "public-untrusted"):
        p = default_policy(profile)
        assert p.profile == profile


def test_unknown_profile_rejected():
    with pytest.raises(ValueError):
        default_policy("yolo")


def test_static_denies_process_and_network():
    p = default_policy("static")
    with pytest.raises(PolicyViolation):
        check_process(p, ["python", "--version"])
    with pytest.raises(PolicyViolation):
        check_network(p, "example.com")


def test_local_trusted_allows_process():
    p = default_policy("local-trusted")
    check_process(p, ["python", "--version"])  # must not raise


def test_classroom_allowlists_network():
    p = GrantedPolicy(
        profile="classroom",
        network="allowlist",
        allow_network_hosts=("example.com",),
        process="sandbox",
    )
    check_network(p, "example.com")
    with pytest.raises(PolicyViolation):
        check_network(p, "evil.example")


def test_public_untrusted_denies_by_default():
    p = default_policy("public-untrusted")
    with pytest.raises(PolicyViolation):
        check_process(p, ["ffmpeg"])
    with pytest.raises(PolicyViolation):
        check_fs_read(p, "./assets/img.png")
