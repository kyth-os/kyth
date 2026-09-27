# Release Support

KythOS publishes a stable channel and a testing channel.

## Channels

| Channel | Tag | Support expectation |
| --- | --- | --- |
| Stable | `latest` | Supported for daily use. Security fixes and important regressions are prioritized here. |
| Testing | `testing` | Development preview. May contain incomplete features or regressions. |

## Update Model

KythOS uses atomic `bootc` deployments. Updates are staged before reboot and the
previous deployment remains available from the boot menu. This means a bad
update should usually be recoverable without reinstalling.

## Security Fixes

Security fixes are provided for the current stable channel. Testing receives
fixes as part of normal development and may receive them before stable while a
change is being validated.

## End of Support

KythOS does not maintain long-term old release lines. Channel releases move
forward. Users who need security fixes should update to the current stable
channel unless a specific advisory says otherwise.

## Immutable vs. Channel Artifacts

Every publish produces **two** artifact sets per channel:

| Kind | GitHub release tag | R2 ISO name | Mutability |
| --- | --- | --- | --- |
| Immutable | `iso-{testing,latest}-{release_id}` (e.g. `iso-testing-20260918-abcdef01-42-1`) | `kyth-live-{tag}-{release_id}.iso` | Never overwritten or deleted |
| Channel pointer | `iso-testing` / `iso-latest` | `kyth-live-testing.iso` / `kyth-live-latest.iso` | Overwritten in place on every publish |

The channel pointer is what users download. The immutable set is the
audit trail and the rollback source. Container images follow the same
model: per-version `image-{VERSION}` releases plus the moving
`:latest` / `:testing` tags.

## Channel Rollback

Use this when a published channel is bad and the fix is to repoint the
channel at the previous immutable build — not to ship a new one.
On-device recovery (`bootc rollback`) is separate and stays available
regardless; this procedure repairs the *published channel* so new
installs and upgrades stop picking up the bad build.

> Old timestamped artifacts are not patched: a rollback also rolls back
> any security fixes shipped after the previous immutable build. Treat a
> rolled-back channel as a stopgap and roll forward with a fixed build as
> soon as one is ready.

Prerequisites: `gh` authenticated against this repo, and R2 credentials
(`R2_ENDPOINT_URL` or `R2_ACCOUNT_ID`, `AWS_ACCESS_KEY_ID`,
`AWS_SECRET_ACCESS_KEY`) for the `kyth-releases` bucket.

1. Identify the bad and previous immutable tags (example: `testing`):

```bash
TAG=testing
gh release list --limit 30 --json tagName \
  -q '.[] | .tagName | select(startswith("iso-'"${TAG}"'-"))'
```

Pick `BAD` (current) and `PREV` (the last known-good immutable tag).

2. Fetch the previous immutable ISO and verify it before promoting:

```bash
gh release download "${PREV}" \
  -p 'kyth-live-'"${TAG}"'-*.iso' \
  -p 'kyth-live-'"${TAG}"'-*.iso-CHECKSUM'
sha256sum --check --strict kyth-live-"${TAG}"-*.iso-CHECKSUM
```

The check must pass. For the strongest guarantee, also verify the
Cosign signature/bundle attached to the `${PREV}` release before use.

3. Repoint the R2 channel files at the previous immutable build. The
immutable R2 objects are never overwritten, so copy them over the
channel names (plus `-CHECKSUM`, `.sig`, `.bundle`, `.intoto.jsonl`,
`.json` sidecars):

```bash
IMM=kyth-live-"${TAG}"-...iso   # full previous immutable basename from step 1
CHAN=kyth-live-"${TAG}".iso
for suffix in '' -CHECKSUM .sig .bundle .intoto.jsonl .json; do
  aws s3 cp "s3://kyth-releases/${IMM}${suffix}" \
    "s3://kyth-releases/${CHAN}${suffix}" \
    --endpoint-url "${R2_ENDPOINT_URL}"
done
```

4. Repoint the channel GitHub release at the previous immutable build.
The channel release is delete-and-recreate by design (see
`build_files/scripts/publish-release.py`); point it at the previous
source commit and link the previous immutable release in the notes:

```bash
PREV_SHA="$(gh release view "${PREV}" --json targetCommitish -q .targetCommitish)"
gh release delete "iso-${TAG}" --yes
gh release create "iso-${TAG}" --target "${PREV_SHA}" \
  --title "Kyth Live ISO - ${TAG} (rollback to ${PREV})" \
  --notes "Channel rolled back to immutable release ${PREV}. See that release for the changelog, checksum, and signatures."
```

5. Confirm the channel serves the rolled-back bytes:

```bash
curl -fsSL -o /tmp/chan.iso "https://pub-9a3cc72972ea44c4ae7504ee7cda1fa6.r2.dev/${CHAN}"
curl -fsSL -o /tmp/chan.iso-CHECKSUM "https://pub-9a3cc72972ea44c4ae7504ee7cda1fa6.r2.dev/${CHAN}-CHECKSUM"
(cd /tmp && sha256sum --check --strict chan.iso-CHECKSUM)
```

(The public download base URL is single-sourced from
`R2_PUBLIC_BASE_URL` in `build_files/scripts/release_identity.py` —
update it there, not in copies.)

Container image rollback follows the same repoint logic: copy the
previous immutable digest back onto the channel tag (e.g.
`crane copy "ghcr.io/kyth-os/kyth@${PREV_DIGEST}" "ghcr.io/kyth-os/kyth:${TAG}"`),
then verify with `cosign verify` and the pinned digest before
announcing. The previous digest for an ISO release is recorded in its
release notes as `Source image digest`.

## Verifying a Download

Every ISO ships with a `-CHECKSUM` sidecar next to it on R2 and on its
immutable GitHub release. Verify before writing to USB:

```bash
curl -fsSL -O https://pub-9a3cc72972ea44c4ae7504ee7cda1fa6.r2.dev/kyth-live-latest.iso
curl -fsSL -O https://pub-9a3cc72972ea44c4ae7504ee7cda1fa6.r2.dev/kyth-live-latest.iso-CHECKSUM
sha256sum --check --strict kyth-live-latest.iso-CHECKSUM
```

A passing check confirms the bytes match the published build. The
`.sig` / `.bundle` / `.intoto.jsonl` attachments on the immutable
GitHub release additionally bind the ISO to its build provenance via
Cosign and GitHub attestation — check those when the download source
is untrusted.

## Reinstall vs. Upgrade

Most changes should be delivered through `bootc upgrade`. A reinstall should be
required only for installer-specific defects, disk layout choices, or documented
breaking changes that cannot be safely migrated in place.
