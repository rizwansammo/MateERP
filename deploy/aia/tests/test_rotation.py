"""Offline tests for crash-safe, 90-day automatic MateERP AIA token rotation."""
import contextlib
import importlib.util
import io
import os
import stat
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

MODULE_PATH = Path(__file__).resolve().parents[1] / "rotate.py"
spec = importlib.util.spec_from_file_location("aia_rotate", MODULE_PATH)
rotate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rotate)


def fake_token(tag):
    return f"aia_{tag * 16}_{tag.upper() * 48}".encode("ascii")


class RotateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        root.chmod(0o700)
        token = root / "token"
        previous = root / "token.previous"
        self.root = root
        self.token = token
        self.previous = previous
        self.context = contextlib.ExitStack()
        self.addCleanup(self.context.close)
        self.context.enter_context(mock.patch.object(rotate, "ROOT", root))
        self.context.enter_context(mock.patch.object(rotate, "TOKEN", token))
        self.context.enter_context(mock.patch.object(rotate, "PREVIOUS", previous))
        self.context.enter_context(mock.patch.object(rotate, "LOCK", root / ".lock"))
        self.context.enter_context(mock.patch.object(rotate.os, "geteuid", return_value=0))
        original = Path.stat

        def owner_is_root(path, *args, **kwargs):
            real = original(path, *args, **kwargs)
            if path in (root, token, previous):
                return SimpleNamespace(
                    st_uid=0, st_mode=real.st_mode, st_mtime=real.st_mtime
                )
            return real

        self.context.enter_context(mock.patch.object(Path, "stat", owner_is_root))

    def save(self, content):
        self.token.write_bytes(content + b"\n")
        self.token.chmod(0o600)

    def test_initial_bootstrap_without_exposing_plaintext(self):
        value = fake_token("a")
        with (
            mock.patch.object(rotate, "issue", return_value=value),
            mock.patch.object(rotate, "verify") as verify,
            mock.patch.object(rotate, "revoke") as revoke,
            contextlib.redirect_stdout(io.StringIO()) as printed,
        ):
            rotate.rotate()
        self.assertEqual(rotate.load(self.token), value)
        self.assertFalse(self.previous.exists())
        self.assertFalse(self.token.stat().st_mode & 0o077)
        verify.assert_called_once_with(value)
        revoke.assert_not_called()
        self.assertNotIn(value.decode(), printed.getvalue())

    def test_recent_token_is_not_rotated(self):
        old = fake_token("b")
        self.save(old)
        with mock.patch.object(rotate, "issue") as issue:
            rotate.rotate()
        issue.assert_not_called()
        self.assertEqual(rotate.load(self.token), old)

    def test_due_token_rotates_then_revokes_original(self):
        old, new = fake_token("a"), fake_token("b")
        self.save(old)
        when = time.time() - 61 * 24 * 3600
        os.utime(self.token, (when, when))
        with (
            mock.patch.object(rotate, "issue", return_value=new),
            mock.patch.object(rotate, "verify") as verify,
            mock.patch.object(rotate, "revoke") as revoke,
        ):
            rotate.rotate()
        self.assertEqual(rotate.load(self.token), new)
        self.assertFalse(self.previous.exists())
        verify.assert_called_once_with(new)
        revoke.assert_called_once_with(old)

    def test_verification_failure_keeps_original_and_revokes_candidate(self):
        old, new = fake_token("a"), fake_token("b")
        self.save(old)
        when = time.time() - 61 * 24 * 3600
        os.utime(self.token, (when, when))
        with (
            mock.patch.object(rotate, "issue", return_value=new),
            mock.patch.object(rotate, "verify", side_effect=rotate.RotationError("denied")),
            mock.patch.object(rotate, "revoke") as revoke,
        ):
            with self.assertRaises(rotate.RotationError):
                rotate.rotate()
        self.assertEqual(rotate.load(self.token), old)
        self.assertFalse(self.previous.exists())
        revoke.assert_called_once_with(new)

    def test_crash_after_swap_revokes_previous_on_next_run(self):
        old, new = fake_token("a"), fake_token("b")
        self.save(new)
        self.previous.write_bytes(old + b"\n")
        self.previous.chmod(0o600)
        with mock.patch.object(rotate, "revoke") as revoke:
            rotate.recover_previous()
        revoke.assert_called_once_with(old)
        self.assertFalse(self.previous.exists())
        self.assertEqual(rotate.load(self.token), new)

    def test_crash_before_swap_does_not_revoke_current(self):
        old = fake_token("a")
        self.save(old)
        os.link(self.token, self.previous)
        with mock.patch.object(rotate, "revoke") as revoke:
            rotate.recover_previous()
        revoke.assert_not_called()
        self.assertFalse(self.previous.exists())
        self.assertEqual(rotate.load(self.token), old)

    def test_file_permissions_are_enforced(self):
        self.save(fake_token("a"))
        self.token.chmod(0o644)
        with self.assertRaises(rotate.RotationError):
            rotate.load(self.token)

    def test_writes_only_allowed_token_shape(self):
        self.assertEqual(rotate.prefix(fake_token("c")), "c" * 16)
        with self.assertRaises(rotate.RotationError):
            rotate.prefix(b"invalid")

    def test_http_smoke_checks_both_allow_and_deny(self):
        value = fake_token("a")
        with mock.patch.object(rotate, "status", side_effect=[200, 403]) as status:
            rotate.verify(value)
        self.assertEqual(status.call_count, 2)
        with mock.patch.object(rotate, "status", side_effect=[200, 200]):
            with self.assertRaises(rotate.RotationError):
                rotate.verify(value)


if __name__ == "__main__":
    unittest.main()
