#!/bin/bash
# Install a current upstream Node LTS runtime over Fedora's compatibility RPMs.
set -euo pipefail

NODEJS_VERSION="${NODEJS_VERSION:-24.15.0}"
install_root="/usr/lib/kyth-nodejs"

case "$(uname -m)" in
x86_64)
	archive_arch="x64"
	expected_sha="472655581fb851559730c48763e0c9d3bc25975c59d518003fc0849d3e4ba0f6"
	;;
aarch64)
	archive_arch="arm64"
	expected_sha="f3d5a797b5d210ce8e2cb265544c8e482eaedcb8aa409a8b46da7e8595d0dda0"
	;;
*)
	echo "ERROR: unsupported Node.js architecture: $(uname -m)" >&2
	exit 1
	;;
esac

archive="node-v${NODEJS_VERSION}-linux-${archive_arch}.tar.xz"
url="https://nodejs.org/dist/v${NODEJS_VERSION}/${archive}"
tmp_dir="$(mktemp -d)"
trap 'rm -rf "${tmp_dir}"' EXIT

curl --fail --location --retry 5 --retry-delay 2 \
	--output "${tmp_dir}/${archive}" "${url}"
echo "${expected_sha}  ${tmp_dir}/${archive}" | sha256sum --check --strict

mkdir -p "${install_root}"
tar --extract --xz --file "${tmp_dir}/${archive}" \
	--strip-components=1 --directory "${install_root}"

# Fedora's npm reads /etc/npmrc, while the upstream archive resolves its
# global config relative to the runtime prefix. Keep both on the same policy.
mkdir -p "${install_root}/etc"
ln -sfn /etc/npmrc "${install_root}/etc/npmrc"

for command in node npm npx corepack; do
	ln -sfn "${install_root}/bin/${command}" "/usr/bin/${command}"
done

node -e 'const [major, minor] = process.versions.node.split(".").map(Number); if (major < 24 || (major === 24 && minor < 15)) process.exit(1)'
npm_prefix="$(HOME=/tmp/kyth-npm-prefix-check npm config get prefix)"
[[ "${npm_prefix}" == "/tmp/kyth-npm-prefix-check/.local" ]] || {
	echo "ERROR: npm global prefix is not user-writable: ${npm_prefix}" >&2
	exit 1
}

node --version
npm --version
