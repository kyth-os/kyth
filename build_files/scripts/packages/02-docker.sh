#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

### Install Docker for container operations
# container-selinux provides the SELinux policy module for container runtimes
# (docker_t, container_t, etc.) — required for Docker to work under enforcing.
dnf5 install -y docker container-selinux
