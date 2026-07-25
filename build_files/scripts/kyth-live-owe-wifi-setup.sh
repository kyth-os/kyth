#!/usr/bin/bash
# Seed explicit Enhanced Open (OWE) Wi-Fi profiles in the ephemeral live
# session. OWE/OWE transition-mode networks can look like plain open Wi-Fi in
# Plasma, so NetworkManager needs a profile with wifi-sec.key-mgmt=owe before
# it can be activated correctly. Installed by installer/build.sh to
# /usr/libexec/kyth-live-owe-wifi-setup and run by kyth-live-owe-wifi.service.
set -euo pipefail

if ! grep -qw 'kyth.live=1' /proc/cmdline 2>/dev/null; then
	exit 0
fi

command -v nmcli >/dev/null 2>&1 || exit 0

LOG_FILE="/var/log/kyth-live-owe-wifi-setup.log"

log() {
	echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >>"${LOG_FILE}"
}

log "Starting OWE Wi-Fi profile setup"

# Wait for NetworkManager to be fully operational
for _try in 1 2 3 4 5 6 7 8 9 10; do
	if nmcli general status 2>/dev/null | grep -q 'connected\|disconnected'; then
		log "NetworkManager is ready (attempt $_try/10)"
		break
	fi
	if [[ $_try -eq 10 ]]; then
		log "ERROR: NetworkManager did not become ready after 10 attempts (20 seconds)"
		exit 1
	fi
	sleep 2
done

if ! nmcli radio wifi on 2>/dev/null; then
	log "WARNING: nmcli radio wifi on failed"
fi
sleep 1

# Scan for OWE networks
declare -A owe_ssids=()
for _try in 1 2 3 4 5 6; do
	log "Scan attempt $_try/6"
	while IFS=: read -r ssid security; do
		[[ -n "${ssid}" && "${ssid}" != "--" ]] || continue
		[[ "${security}" == *OWE* ]] || continue
		owe_ssids["${ssid}"]=1
		log "Found OWE network: ${ssid}"
	done < <(nmcli --escape no -t -f SSID,SECURITY device wifi list --rescan yes 2>/dev/null || true)

	if [[ "${#owe_ssids[@]}" -gt 0 ]]; then
		log "Found OWE networks on attempt $_try/6, proceeding"
		break
	fi
	sleep 2
done

if [[ "${#owe_ssids[@]}" -eq 0 ]]; then
	log "No OWE networks found after 6 scans, exiting"
	exit 0
fi

log "Found ${#owe_ssids[@]} OWE network(s), setting up profiles"

for ssid in "${!owe_ssids[@]}"; do
	con_name="Kyth OWE ${ssid}"
	log "Processing SSID: ${ssid} (connection: ${con_name})"

	# Always delete and recreate to avoid state corruption on reboot
	if nmcli connection delete "${con_name}" 2>/dev/null; then
		log "Deleted existing connection: ${con_name}"
	fi

	# Create the OWE profile with all required settings
	if nmcli connection add \
		type wifi \
		ifname "*" \
		con-name "${con_name}" \
		ssid "${ssid}" \
		wifi-sec.key-mgmt owe \
		ipv4.method auto \
		ipv4.dhcp-send-hostname yes \
		ipv4.ignore-auto-dns no \
		connection.autoconnect no \
		connection.permissions "" \
		2>/tmp/kyth-owe-error.log; then

		# Validate the profile was created with correct settings
		key_mgmt=$(nmcli -g 802-11-wireless-security.key-mgmt connection show "${con_name}" 2>/dev/null || echo "ERROR")
		ipv4_method=$(nmcli -g ipv4.method connection show "${con_name}" 2>/dev/null || echo "ERROR")

		if [[ "${key_mgmt}" == "owe" && "${ipv4_method}" == "auto" ]]; then
			log "✓ Profile created successfully: ${con_name}"
		else
			log "ERROR: Profile validation failed for ${con_name}"
			log "  key-mgmt: ${key_mgmt}"
			log "  ipv4.method: ${ipv4_method}"
		fi
	else
		log "ERROR: Failed to create connection ${con_name}"
		cat /tmp/kyth-owe-error.log >>"${LOG_FILE}" 2>/dev/null || true
	fi
done

# Auto-connect if exactly one OWE network and no WiFi connected
wifi_connected=$(nmcli -t -f DEVICE,TYPE,STATE device status 2>/dev/null | grep -c ':wifi:connected' || echo 0)
if [[ "${#owe_ssids[@]}" -eq 1 && "${wifi_connected}" -eq 0 ]]; then
	for ssid in "${!owe_ssids[@]}"; do
		con_name="Kyth OWE ${ssid}"
		log "Single OWE network with no WiFi connected, attempting auto-connect: ${con_name}"
		if nmcli connection up "${con_name}" 2>/tmp/kyth-owe-error.log; then
			log "✓ Successfully brought up connection: ${con_name}"
		else
			log "ERROR: Failed to bring up ${con_name}"
			cat /tmp/kyth-owe-error.log >>"${LOG_FILE}" 2>/dev/null || true
		fi
	done
else
	log "Skipping auto-connect: ${#owe_ssids[@]} OWE networks, ${wifi_connected} WiFi connections active"
fi

log "OWE Wi-Fi profile setup complete"
