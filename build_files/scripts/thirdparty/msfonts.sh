# shellcheck shell=bash
install_msfonts() {
	# Microsoft "Core Fonts for the Web" — legally redistributable TrueType fonts
	# shipped by Windows since the late 1990s. Arial, Times New Roman, Verdana,
	# Georgia, Courier New, Impact, Trebuchet MS, Comic Sans, Andale Mono, Webdings.
	# Required for correct rendering of Office documents and many websites that
	# hard-code "Arial" or "Times New Roman" without web-safe fallbacks.
	# Without these fonts, LibreOffice substitutes Liberation metrics-compatible
	# equivalents which are visually close but not pixel-identical to Windows.
	local tmp
	tmp=$(mktemp -d)

	local sf_base="https://downloads.sourceforge.net/project/corefonts/the%20fonts/final"
	# The corefonts installers have been immutable since 2002 — pin their
	# sha256 sums so SourceForge mirrors are held to the same integrity bar as
	# every GitHub release this script installs.
	local -A exe_sha256=(
		[andale32.exe]=0524fe42951adc3a7eb870e32f0920313c71f170c859b5f770d82b4ee111e970
		[arial32.exe]=85297a4d146e9c87ac6f74822734bdee5f4b2a722d7eaa584b7f2cbf76f478f6
		[arialb32.exe]=a425f0ffb6a1a5ede5b979ed6177f4f4f4fdef6ae7c302a7b7720ef332fec0a8
		[comic32.exe]=9c6df3feefde26d4e41d4a4fe5db2a89f9123a772594d7f59afd062625cd204e
		[courie32.exe]=bb511d861655dde879ae552eb86b134d6fae67cb58502e6ff73ec5d9151f3384
		[georgi32.exe]=2c2c7dcda6606ea5cf08918fb7cd3f3359e9e84338dc690013f20cd42e930301
		[impact32.exe]=6061ef3b7401d9642f5dfdb5f2b376aa14663f6275e60a51207ad4facf2fccfb
		[times32.exe]=db56595ec6ef5d3de5c24994f001f03b2a13e37cee27bc25c58f6f43e8f807ab
		[trebuc32.exe]=5a690d9bb8510be1b8b4fe49f1f2319651fe51bbe54775ddddd8ef0bd07fdac9
		[verdan32.exe]=c1cb61255e363166794e47664e2f21af8e3a26cb6346eb8d2ae2fa85dd5aad96
		[webdin32.exe]=64595b5abc1080fba8610c5c34fab5863408e806aafe84653ca8575bed17d75a
	)
	local -a exes=(
		andale32.exe arial32.exe arialb32.exe comic32.exe courie32.exe
		georgi32.exe impact32.exe times32.exe trebuc32.exe verdan32.exe
		webdin32.exe
	)

	local failed=0
	for exe in "${exes[@]}"; do
		if ! curl --retry 3 --retry-delay 3 -fsSL -o "${tmp}/${exe}" "${sf_base}/${exe}"; then
			echo "msfonts: failed to download ${exe}" >&2
			((failed++)) || true
		fi
	done

	if [[ $failed -gt 0 ]]; then
		rm -rf "$tmp"
		echo "msfonts: ${failed} download(s) failed — skipping font install" >&2
		return 1
	fi

	local actual
	for exe in "${exes[@]}"; do
		actual=$(sha256sum "${tmp}/${exe}" | awk '{print $1}')
		if [[ "${actual}" != "${exe_sha256[${exe}]}" ]]; then
			rm -rf "$tmp"
			echo "ERROR: msfonts: SHA256 mismatch for ${exe}!" >&2
			echo "  Expected: ${exe_sha256[${exe}]}" >&2
			echo "  Got:      ${actual}" >&2
			exit 1
		fi
	done
	echo "msfonts: all ${#exes[@]} installers SHA256 verified OK"

	mkdir -p /usr/share/fonts/msttcorefonts
	for exe in "${exes[@]}"; do
		local exdir="${tmp}/x_${exe%.exe}"
		mkdir -p "$exdir"
		# Cabinet archives may fail silently on non-font files; extract what we can.
		cabextract -q -d "$exdir" "${tmp}/${exe}" 2>/dev/null || true
		find "$exdir" -iname "*.ttf" -exec cp {} /usr/share/fonts/msttcorefonts/ \;
	done

	# Some cabinets ship uppercase .TTF — normalize to lowercase for consistent queries.
	find /usr/share/fonts/msttcorefonts -name "*.TTF" | while IFS= read -r f; do
		mv "$f" "${f%.TTF}.ttf"
	done

	local count
	count=$(find /usr/share/fonts/msttcorefonts -name "*.ttf" | wc -l)
	fc-cache -f /usr/share/fonts/msttcorefonts
	rm -rf "$tmp"
	echo "msfonts: installed ${count} TrueType fonts"
}
