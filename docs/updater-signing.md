# Updater manifest signing

**Status:** implemented 2026-10-19 (decision approved by Patrick the same
day). **Scope:** the `kyth-rclone-update` and `kyth-proton-cachyos-update`
runtime updaters. **Code:** `src/kyth-shared-rs/src/system/update_manifest.rs`,
gated call sites in `rclone_update_bin.rs` and
`proton_cachyos_update_bin.rs`.

## Why this exists

Both runtime updaters historically verified downloads against a checksum
fetched from the same release as the artifact itself — rclone against its
published `SHA256SUMS`, GE-Proton against the release's `.sha512sum`
sidecar. That proves a download was not corrupted in transit. It does not
prove the release is genuine: a compromised upstream account or release
page replaces the file and its checksum together, and the updater installs
both without a murmur.

The fix is a small **update manifest**, signed offline with a KythOS
signing key, that approves a specific `(component, version, artifact,
digest)` tuple. An updater installs a version only when:

1. the manifest's OpenPGP signature verifies against the KythOS signing
   primary key baked into the image, **and**
2. the manifest approves the exact version and artifact being installed,
   **and**
3. the downloaded artifact hashes to the digest the signed manifest
   pinned — *in addition to* the existing upstream checksum verification,
   which still runs unchanged.

Every failure is **fail closed**: the update is refused, the currently
installed version keeps running, and the failure is reported through the
updater's normal error output. The previous version is never removed
before its replacement is installed and verified, so a rejected update
rolls back by doing nothing.

A consequence of the design: a brand-new upstream release becomes
installable only after a signed manifest approves it. Approval is a
deliberate human step in the release flow (see *Release flow* below), not
an automatic pass-through.

## Manifest format

Published as `kyth-updater-manifest.json` at the root of the KythOS
public release bucket
(`https://pub-9a3cc72972ea44c4ae7504ee7cda1fa6.r2.dev/`), next to its
detached signature `kyth-updater-manifest.json.asc` and the current
signing certificate `kyth-updater-keys.asc`.

```json
{
  "schema": 1,
  "issued": "2026-10-19T00:00:00Z",
  "updates": [
    {
      "component": "rclone",
      "version": "v1.68.2",
      "artifact": "rclone-v1.68.2-linux-amd64.zip",
      "sha256": "<64 lowercase hex chars>"
    },
    {
      "component": "ge-proton",
      "version": "GE-Proton10-15",
      "artifact": "GE-Proton10-15-x86_64.tar.gz",
      "sha512": "<128 lowercase hex chars>"
    }
  ]
}
```

- `schema` — only `1` is understood by current builds. An unknown schema
  is refused, never half-interpreted.
- `updates[]` — exactly one entry must match the `(component, version,
  artifact)` being installed. Zero matches means "not approved";
  duplicates mean the manifest is ambiguous. Both refuse the install.
- Each entry must carry the digest its updater checks (`sha256` for
  rclone, `sha512` for GE-Proton). An entry missing the needed digest is
  a refusal: the signature only vouches for values actually present.

The signature is a detached OpenPGP signature over the **exact bytes** of
the JSON file as published. The manifest is parsed only after the
signature verifies.

## Signature verification

Verification uses the pure-Rust **rPGP** crate (`pgp` 0.19), verify-only —
no signing capability exists anywhere in the shipped code. (Sequoia was
considered and rejected: its RustCrypto backend refuses to build without
an experimental opt-in because upstream does not consider it production
ready. rPGP builds identically on the dev VM, in CI, and in the Fedora
image with no system crypto libraries.)

For a manifest to be accepted, all of the following must hold:

1. The image's trust anchor (below) contains at least one parseable
   public certificate.
2. The published `kyth-updater-keys.asc` contains a certificate whose
   **primary key fingerprint matches an anchor certificate**. Only the
   primary is pinned; the fetched certificate supplies the primary's
   current subkeys.
3. That certificate's self-signatures verify (`verify_bindings()`), so a
   subkey counts only when the trusted primary actually bound it — a
   substituted subkey riding on the public primary key does not work.
4. The detached signature validates over the manifest bytes under the
   primary key or one of its bound subkeys. rPGP's signature check also
   enforces issuer identity and hash-strength policy.

Accepted limitation: the verifier does not evaluate certificate expiry
or revocation status. Rotation and retirement are effected by
**republication** — the published certificate is the authority for which
subkeys exist (see *Rotation*). Dropping a subkey from the published
certificate retires it, because signatures are only checked against keys
the published, anchor-matching certificate actually carries.

## Trust anchor and the placeholder state

The trust anchor is `/usr/share/kyth/updater-signing-keys.asc` on
installed systems, installed from `build_files/config/updater-signing-keys.asc`
by `build_files/scripts/branding/99-updater-signing-key.sh`. It holds
**public certificates only** — there is nothing in the image, the repo,
or on a user's machine that can sign an update.

As shipped, the anchor is a **placeholder**: comments only, no key
material, because the production key does not exist yet (it is generated
later, offline, on the key owner's own hardware — see *Key ceremony*).
While the placeholder is in place, every gated update is refused with an
explicit "no KythOS updater signing key is installed yet" error. That is
the intended behaviour, not a bypass: the mechanism ships complete and
fail-closed, and updates resume once a real key ships in an image update
and the first signed manifest is published.

Verification inputs can be overridden by environment for testing and
recovery: `KYTH_UPDATER_KEYRING_PATH`, `KYTH_UPDATER_MANIFEST_URL`,
`KYTH_UPDATER_MANIFEST_SIGNATURE_URL`, `KYTH_UPDATER_KEYS_URL`.

## Where the gate hooks in

- **rclone** (`kyth-rclone-update`): after the target version is resolved
  and the workdir exists, before anything is downloaded. On approval, the
  existing upstream `SHA256SUMS` verification runs as before, then the
  archive must also hash to the manifest-pinned sha256.
- **GE-Proton** (`kyth-proton-cachyos-update`): after the up-to-date
  check, before the incomplete-install cleanup and any download. On
  approval, the existing upstream `.sha512sum` verification runs as
  before, then the tarball must also hash to the manifest-pinned sha512.

In both cases a gate failure exits through the updater's existing failure
path — nothing is downloaded or installed, and the current version is
untouched.

## Key ceremony (key owner, offline, once)

Perform on the key owner's own hardware, ideally an offline environment.
Never on a build machine, never in CI, never by an automated tool. No
agent ever handles this key material.

1. Generate a primary key that can certify, plus a signing subkey for
   day-to-day manifest signing, e.g. with `gpg --quick-generate-key`
   followed by `gpg --quick-add-key <fingerprint> ed25519 sign` (an
   Ed25519 or RSA signing subkey both verify; match the tooling you are
   comfortable maintaining).
2. Keep the primary key offline (encrypted drive or hardware token).
   Make one encrypted backup in a second physical location. The real
   risk is **loss**, not theft: lose the primary and its backup, and
   updates stay refused until a new key ships in an image update.
3. Export only the public certificate:
   `gpg --armor --export <key-id> > updater-signing-keys.asc`
4. Replace the contents of `build_files/config/updater-signing-keys.asc`
   with that public block and commit it on `testing`. The key reaches
   installed systems with the next image update.
5. Publish the same certificate as `kyth-updater-keys.asc` at the
   release bucket root (step 2 of the release flow).

## Release flow (per rclone / GE-Proton version bump)

1. Generate the unsigned manifest on any connected machine:
   `build_files/scripts/generate-updater-manifest.py`
   It resolves the current rclone and GE-Proton releases and their
   digests and writes `kyth-updater-manifest.json`. It never signs
   anything. (`GITHUB_TOKEN` in the environment avoids GitHub API rate
   limits.)
2. On the key owner's hardware, review the manifest, then sign it
   offline with the signing subkey:
   `gpg --armor --detach-sign --output kyth-updater-manifest.json.asc kyth-updater-manifest.json`
3. Upload all three files to the release bucket root:
   `kyth-updater-manifest.json`, `kyth-updater-manifest.json.asc`, and a
   current export of the signing certificate as `kyth-updater-keys.asc`.
   Nothing installs until all three are published and the signature
   verifies.

To roll back a signed-but-bad update, generate and sign a manifest whose
entry points back at the last good version and publish it the same way —
no emergency key handling.

## Rotation

**Signing subkey** (yearly, or immediately on any suspicion) — no image
update needed:

1. On the offline hardware, add a new signing subkey to the primary and
   retire the old one.
2. Re-export the public certificate and publish it as
   `kyth-updater-keys.asc`. Because the image pins only the primary
   fingerprint, updaters accept signatures from the new subkey as soon as
   the amended certificate is published. Signatures from a subkey that
   is no longer in the published certificate stop verifying.

**Primary key** (only if the primary itself is in doubt):

1. Generate the new primary offline as in the key ceremony.
2. Ship an anchor file containing **both** the old and the new primary
   certificates in an image update (the anchor parser accepts several
   certificates, in one armor block or concatenated blocks).
3. Publish the new certificate as `kyth-updater-keys.asc` and sign new
   manifests with the new key. Both primaries verify during the overlap,
   so no machine is stranded.
4. Once the overlap has ridden out, ship an image update whose anchor
   drops the old primary.

## Failure semantics

| Condition | Result |
| --- | --- |
| Placeholder / missing / unparseable anchor | Refuse; "signing key not installed yet" |
| Manifest, signature, or key file unreachable | Refuse |
| Published key file has no anchor-matching certificate | Refuse |
| Certificate self-signatures broken | Refuse |
| Signature invalid or over different bytes | Refuse |
| Manifest schema unknown | Refuse |
| No entry approves the resolved version/artifact | Refuse |
| Entry lacks the needed digest, or digest malformed | Refuse |
| Artifact digest ≠ manifest-pinned digest | Refuse (after upstream checksum still passes) |
| Upstream checksum verification fails | Refuse (pre-existing behaviour, unchanged) |

In every refusal the updater exits through its existing failure path and
the currently installed version keeps running.
