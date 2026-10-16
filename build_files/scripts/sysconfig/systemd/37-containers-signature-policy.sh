#!/bin/bash
# shellcheck shell=bash
# 37-containers-signature-policy — install containers/image signature policy.
#
# Enforces sigstore signature verification for ghcr.io/kyth-os/kyth image
# pulls (including `bootc upgrade` in the update watcher). The policy pins a
# static Cosign public key; the supply-chain workflow signs image and SBOM
# digests with its matching encrypted private-key secret.
#
# Without this, Fedora's default insecureAcceptAnything applies and the
# update path never verifies the cosign signatures.
set -euo pipefail

install -Dm 0644 /ctx/config/containers/policy.json /etc/containers/policy.json
install -Dm 0644 /ctx/config/containers/registries.d/kyth.yaml /etc/containers/registries.d/kyth.yaml
install -Dm 0644 /ctx/config/containers/kyth-cosign.pub /etc/containers/kyth-cosign.pub

# Validate the policy parses as JSON with the expected native static-key rule.
python3 - <<'PY'
import json
policy = json.load(open("/etc/containers/policy.json"))
reqs = policy["transports"]["docker"]["ghcr.io/kyth-os/kyth"]
assert reqs[0]["type"] == "sigstoreSigned", "kyth policy must require sigstoreSigned"
assert reqs[0]["keyPath"] == "/etc/containers/kyth-cosign.pub", "kyth policy must use the installed static key"
assert "fulcio" not in reqs[0], "native static-key policy must not use Fulcio fields"
assert reqs[0]["signedIdentity"]["type"] == "matchRepository", "signature must match the Kyth repository"
print("containers signature policy installed and validated")
PY
