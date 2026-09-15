"""``updates.pause_while_active``: the update gate is optional and visible.

Contract: the concurrent-instance preflight refuses to start an update while a non-gateway
Hermes session is running, that refusal is configurable (default on), and the state prints
wherever update status is shown. Mirrors the config-opt-out shape of
``tests/hermes_cli/test_passive_update_opt_out.py`` and the gate fixtures of
``tests/hermes_cli/test_update_concurrent_quarantine.py`` (the Windows gate this wraps).
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from hermes_constants import get_hermes_home


def _write_config(body: str) -> None:
    (get_hermes_home() / "config.yaml").write_text(body, encoding="utf-8")


class _StubModules:
    """``_m()`` with a few names overridden — everything else resolves to the real module, so a
    test fakes only the gate's inputs, never the module surface production reads."""

    def __init__(self, real, **overrides):
        self._real, self._overrides = real, overrides

    def __getattr__(self, name):
        if name in self._overrides:
            return self._overrides[name]
        return getattr(self._real(), name)


def test_gate_refuses_while_a_session_runs_and_yields_when_disabled(monkeypatch, capsys):
    from hermes_cli import update_cmd

    args = type("Args", (), {"force": False})()
    running = [(4242, "hermes.exe")]

    def _stub_modules():
        return _StubModules(
            update_cmd._m,
            _is_windows=lambda: True,
            _venv_scripts_dir=lambda: Path("C:/fake/venv/Scripts"),
            _detect_concurrent_hermes_instances=lambda _scripts_dir: list(running),
            _filter_non_gateway_concurrent_instances=lambda matches: list(matches),
        )

    monkeypatch.setattr(update_cmd, "_m", _stub_modules)

    # Absent key: the pause is on, so the run is refused and says why.
    _write_config("updates:\n  pre_update_backup: false\n")
    assert update_cmd._pause_while_active() is True
    try:
        update_cmd._begin_update_receipt_and_plan(args)
    except SystemExit as exc:
        assert exc.code == 2
    else:
        raise AssertionError("the gate did not refuse while a session was running")
    refused = capsys.readouterr().out
    assert "Pause updates while you work: ON" in refused
    assert "pause_while_active" in refused

    # Turned off: the same situation proceeds, loudly, instead of exiting.
    _write_config("updates:\n  pause_while_active: false\n")
    assert update_cmd._pause_while_active() is False
    update_cmd._begin_update_receipt_and_plan(args)
    warned = capsys.readouterr().out
    assert "Pause updates while you work: OFF" in warned
    assert "pause_while_active is off" in warned


def test_update_check_prints_the_pause_state_following_config(tmp_path, monkeypatch, capsys):
    from hermes_cli import main
    from hermes_cli.update_cmd import _cmd_update_check

    remote = tmp_path / "remote"
    local = tmp_path / "checkout"

    def git(*args):
        return subprocess.run(["git", *map(str, args)], check=True, capture_output=True, text=True)

    git("init", "-b", "main", remote)
    git("-C", remote, "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
        "commit", "--allow-empty", "-m", "initial")
    git("clone", remote, local)
    git("-C", remote, "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
        "commit", "--allow-empty", "-m", "next")
    monkeypatch.setattr(main, "PROJECT_ROOT", local)

    _write_config("updates:\n  pause_while_active: true\n")
    _cmd_update_check()
    assert "Pause updates while you work: ON" in capsys.readouterr().out

    _write_config("updates:\n  pause_while_active: false\n")
    _cmd_update_check()
    assert "Pause updates while you work: OFF" in capsys.readouterr().out
