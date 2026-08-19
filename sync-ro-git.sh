#!/bin/bash
# Sync RO .git at /var/home/mrtrick/git/kyth/.git (btrfs ro bind) to writable overlay at /tmp/kyth-git-writable
# Inside toolbox /var/home is a ro bind (host is immutable bootc). Commits use
#   GIT_DIR=/tmp/kyth-git-writable GIT_WORK_TREE=/var/home/mrtrick/git/kyth
# and push via that overlay. After each push/pull, sync the overlay back to the
# RO host .git so plain `git status` is clean. Works inside toolbox via host-spawn
# (host sees /var/home as rw, no sudo needed, and /tmp is shared). On host directly,
# the same rsync works without host-spawn.
set -euo pipefail
if command -v host-spawn >/dev/null 2>&1; then
  echo "Syncing via host-spawn (toolbox) ..."
  host-spawn bash -c "rsync -a /tmp/kyth-git-writable/ /var/home/mrtrick/git/kyth/.git/"
else
  echo "Syncing RO .git -> writable overlay ..."
  rsync -a /tmp/kyth-git-writable/ /var/home/mrtrick/git/kyth/.git/
fi
echo "Done. Verifying:"
echo "RO:"; cat /var/home/mrtrick/git/kyth/.git/refs/heads/testing
echo "Writable:"; cat /tmp/kyth-git-writable/refs/heads/testing
echo "git status (RO):"; git -C /var/home/mrtrick/git/kyth status --porcelain | head -5 || true
echo "git status (writable):"; GIT_DIR=/tmp/kyth-git-writable GIT_WORK_TREE=/var/home/mrtrick/git/kyth git status --porcelain | head -5 || true
