#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

### Install Docker for container operations
# container-selinux provides the SELinux policy module for container runtimes
# (docker_t, container_t, etc.) — required for Docker to work under enforcing.
# runc is a WEAK dep of the docker (moby-engine) package, so image builds that
# disable weak deps drop it — and then dockerd's BuildKit dies at startup with
# "failed to find runc binary". Install it explicitly so every deploy can build.
dnf5 install -y docker container-selinux runc
