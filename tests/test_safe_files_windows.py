"""windows_parents with Windows mkdir semantics, emulated on any OS (no real WinAPI)."""
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services.backups import safe_files


@pytest.fixture
def emulated(monkeypatch):
    opened = []
    monkeypatch.setattr(safe_files, 'winapi', lambda: (None, None, SimpleNamespace(CloseHandle=lambda h: None)))
    monkeypatch.setattr(safe_files, 'win_open', lambda path, **k: opened.append(Path(path)) or 1)
    real_mkdir = Path.mkdir
    def windows_mkdir(self, *a, **k):
        # Windows: CreateDirectory("F:\") -> ERROR_ACCESS_DENIED, not ERROR_ALREADY_EXISTS.
        if self == Path(self.anchor):
            raise PermissionError(13, 'Access is denied')
        if self.name == 'locked-existing' and self.is_dir():
            raise PermissionError(13, 'Access is denied')
        return real_mkdir(self, *a, **k)
    monkeypatch.setattr(Path, 'mkdir', windows_mkdir)
    return opened


def test_drive_anchor_is_never_created_and_missing_parents_are(emulated, tmp_path):
    root = tmp_path / 'emergency'
    root.mkdir()
    with safe_files.windows_parents(root, ('Excel', '2026-11-26_1'), True) as parent:
        assert parent == root / 'Excel' / '2026-11-26_1' and parent.is_dir()
    assert emulated[0] == Path(root.anchor) and emulated[-1] == parent


def test_access_denied_on_existing_directory_is_tolerated(emulated, tmp_path):
    root = tmp_path / 'locked-existing'
    root.mkdir()
    with safe_files.windows_parents(root, ('Excel',), True) as parent:
        assert parent.is_dir()


def test_access_denied_for_missing_directory_still_fails(emulated, tmp_path, monkeypatch):
    real_mkdir = Path.mkdir
    def denied(self, *a, **k):
        if self.name == 'blocked':
            raise PermissionError(13, 'Access is denied')
        return real_mkdir(self, *a, **k)
    monkeypatch.setattr(Path, 'mkdir', denied)
    with pytest.raises(PermissionError):
        with safe_files.windows_parents(tmp_path, ('blocked', 'x'), True):
            pass
