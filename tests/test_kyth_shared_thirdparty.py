"""Tests for kyth_shared.thirdparty module."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch, MagicMock

from kyth_shared.thirdparty import (
    fetch_widevine_version,
    find_latest_davinci_zip,
    prepare_davinci_resolve,
)


def test_fetch_widevine_version_success():
    mock_resp = MagicMock()
    mock_resp.readline.return_value = b"4.10.2710.0\n"
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        ver = fetch_widevine_version()
        assert ver == "4.10.2710.0"


def test_find_latest_davinci_zip(tmp_path: Path):
    zip1 = tmp_path / "DaVinci_Resolve_18_Linux.zip"
    zip1.write_bytes(b"dummy")

    found = find_latest_davinci_zip(download_dir=tmp_path)
    assert found == zip1


def test_prepare_davinci_resolve_studio(tmp_path: Path):
    zip_path = tmp_path / "DaVinci_Resolve_Studio_18.6_Linux.zip"
    zip_path.write_bytes(b"dummy")

    meta = prepare_davinci_resolve(zip_path)
    assert meta["app_id"] == "com.blackmagic.ResolveStudio"
    assert meta["manifest"] == "com.blackmagic.ResolveStudio.yaml"
    assert meta["is_studio"] == "true"
