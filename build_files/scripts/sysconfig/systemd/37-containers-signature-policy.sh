#!/bin/bash
# shellcheck shell=bash
# 37-containers-signature-policy — install containers/image signature policy.
#
# Enforces sigstore signature verification for ghcr.io/kyth-os/kyth image
# pulls (including `bootc upgrade` in the update watcher). Signatures are
# minted keyless by the supply-chain workflow; the policy pins the Fulcio
# OIDC identity to that workflow on main/testing.
#
# Without this, Fedora's default insecureAcceptAnything applies and the
# update path never verifies the cosign signatures.
set -euo pipefail

install -Dm 0644 /ctx/config/containers/policy.json /etc/containers/policy.json
install -Dm 0644 /ctx/config/containers/registries.d/kyth.yaml /etc/containers/registries.d/kyth.yaml

# Validate the policy parses as JSON with the expected structure.
python3 - <<'PY'
import json
policy = json.load(open("/etc/containers/policy.json"))
reqs = policy["transports"]["docker"]["ghcr.io/kyth-os/kyth"]
assert reqs[0]["type"] == "sigstoreSigned", "kyth policy must require sigstoreSigned"
assert "supply-chain" in reqs[0]["fulcio"]["subjectUri"], "policy must pin the supply-chain workflow identity"
print("containers signature policy installed and validated")
PY
