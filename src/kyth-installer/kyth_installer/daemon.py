"""Root-owned Unix-socket service for the installer transport."""

from __future__ import annotations

import argparse
import os
import re
from pathlib import Path

from . import config, server
from .context import InstallerContext

_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{32,512}$")


def _read_session_token(path: Path) -> str:
    """Read a launcher-created token without following links or loose modes."""
    info = os.lstat(path)
    if not os.path.isfile(path) or info.st_mode & 0o077:
        raise RuntimeError("installer session token must be a private regular file")
    if info.st_uid != 0:
        raise RuntimeError("installer session token must be owned by root")
    token = path.read_text(encoding="ascii").strip()
    if not _TOKEN_RE.fullmatch(token):
        raise RuntimeError("installer session token has an invalid format")
    return token


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="KythOS installer Unix-socket service")
    parser.add_argument("--socket-path", required=True)
    parser.add_argument("--session-token-file", required=True)
    parser.add_argument("--socket-group", default="")
    parser.add_argument("--peer-uid", type=int)
    args = parser.parse_args(argv)

    if os.geteuid() != 0:
        parser.error("kyth-installerd must run as root")
    token_path = Path(args.session_token_file)
    token = _read_session_token(token_path)
    # Handler imported this value into its module namespace for the legacy
    # loopback service, so update both values before accepting requests.
    config.SESSION_TOKEN = token
    server.SESSION_TOKEN = token

    service = server.UnixSocketServer(
        args.socket_path,
        server.Handler,
        context=InstallerContext(),
        peer_uid=args.peer_uid,
        socket_group=args.socket_group,
    )
    try:
        service.serve_forever()
    finally:
        service.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
