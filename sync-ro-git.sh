#!/bin/bash
# Sync RO .git at /var/home/mrtrick/git/kyth/.git (btrfs ro bind) to writable overlay at /tmp/kyth-git-writable
# Run this on HOST (outside toolbox) after each `push` via GIT_DIR, or after `git pull` diverges.
set -e
echo "Syncing RO .git (9042922) -> writable (8818dd5) ..."
sudo mount -o remount,rw /var/home/mrtrick/git/kyth/.git
sudo rsync -a /tmp/kyth-git-writable/ /var/home/mrtrick/git/kyth/.git/
sudo mount -o remount,ro /var/home/mrtrick/git/kyth/.git
echo "Done. Verifying:"
echo "RO:"; cat /var/home/mrtrick/git/kyth/.git/refs/heads/testing
echo "Writable:"; cat /tmp/kyth-git-writable/refs/heads/testing
echo "git status (RO):"; git -C /var/home/mrtrick/git/kyth status --porcelain | head -5 || true
echo "git status (writable):"; GIT_DIR=/tmp/kyth-git-writable GIT_WORK_TREE=/var/home/mrtrick/git/kyth git status --porcelain | head -5 || true
