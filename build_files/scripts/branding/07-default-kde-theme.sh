# shellcheck shell=bash
mkdir -p /etc/skel/.config /etc/skel/Screenshots
cp /ctx/data/skel/Screenshots/.directory /etc/skel/Screenshots/.directory
cp /ctx/data/skel/.config/kdeglobals /etc/skel/.config/kdeglobals
cp /ctx/data/skel/.config/kwinrc /etc/skel/.config/kwinrc
cp /ctx/data/skel/.config/plasmarc /etc/skel/.config/plasmarc

window_control_src=/ctx/branding/window-controls
window_control_css=/tmp/kyth-window-controls.css

render_window_control() {
	local source=$1
	local output=$2
	local size=$3
	local background=$4
	local foreground=$5
	write_config "${window_control_css}" <<EOF
.background { fill: ${background}; }
.glyph { fill: ${foreground}; }
EOF
	rsvg-convert -w "${size}" -h "${size}" --stylesheet "${window_control_css}" \
		"${source}" -o "${output}"
}

for gtk_theme in Breeze Breeze-Dark; do
	gtk_assets="/usr/share/themes/${gtk_theme}/assets"
	[[ -d "${gtk_assets}" ]] || continue

	for state in symbolic hover-symbolic active-symbolic; do
		install -m 0644 "${window_control_src}/minimize.svg" \
			"${gtk_assets}/breeze-minimize-${state}.svg"
		install -m 0644 "${window_control_src}/maximize.svg" \
			"${gtk_assets}/breeze-maximize-${state}.svg"
		install -m 0644 "${window_control_src}/maximize.svg" \
			"${gtk_assets}/breeze-maximized-${state}.svg"
	done
	install -m 0644 "${window_control_src}/close.svg" \
		"${gtk_assets}/breeze-close-symbolic.svg"
	sed 's/#ffffff/#ff0404/' "${window_control_src}/close.svg" \
		>"${gtk_assets}/breeze-close-hover-symbolic.svg"
	sed 's/#ffffff/#ff0404/' "${window_control_src}/close.svg" \
		>"${gtk_assets}/breeze-close-active-symbolic.svg"

	if [[ "${gtk_theme}" == Breeze-Dark ]]; then
		normal_fg='rgba(252,252,252,0.91)'
		backdrop_fg='rgba(161,169,177,0.40)'
		hover_bg='#fcfcfc'
		hover_fg='#232629'
	else
		normal_fg='rgba(35,38,41,0.91)'
		backdrop_fg='rgba(112,125,138,0.72)'
		hover_bg='#232629'
		hover_fg='#fcfcfc'
	fi

	for scale in 1 2; do
		if ((scale == 1)); then
			size=18
			suffix=''
		else
			size=36
			suffix='@2'
		fi

		for control in minimize maximize; do
			source="${window_control_src}/${control}.svg"
			render_window_control "${source}" "${gtk_assets}/titlebutton-${control}${suffix}.png" \
				"${size}" none "${normal_fg}"
			render_window_control "${source}" "${gtk_assets}/titlebutton-${control}-hover${suffix}.png" \
				"${size}" "${hover_bg}" "${hover_fg}"
			render_window_control "${source}" "${gtk_assets}/titlebutton-${control}-active${suffix}.png" \
				"${size}" "${hover_bg}" "${hover_fg}"
			render_window_control "${source}" "${gtk_assets}/titlebutton-${control}-backdrop${suffix}.png" \
				"${size}" none "${backdrop_fg}"
		done

		for state in '' '-hover' '-active' '-backdrop'; do
			case "${state}" in
			-hover) close_fg='#ff667c' ;;
			-active) close_fg='#da4453' ;;
			-backdrop) close_fg="${backdrop_fg}" ;;
			*) close_fg="${normal_fg}" ;;
			esac
			render_window_control "${window_control_src}/close.svg" \
				"${gtk_assets}/titlebutton-close${state}${suffix}.png" \
				"${size}" none "${close_fg}"
		done

		for state in '' '-hover' '-active' '-backdrop'; do
			cp "${gtk_assets}/titlebutton-maximize${state}${suffix}.png" \
				"${gtk_assets}/titlebutton-maximize-maximized${state}${suffix}.png"
		done
	done
done
rm -f "${window_control_css}"
