# Kyth privileged action service

`kyth-privileged.service` owns `/run/kyth/privileged.sock` and accepts one
JSON object per line. The service is root-owned, restricted to root/wheel
callers, and accepts only named operations. It never accepts an executable,
shell string, or arbitrary argument vector.

Supported operations are:

- `flatpak_uninstall` with `app_id`
- `firmware_update`
- `nvidia_install`
- `kernel_switch` with `flavor` `fedora` or `cachy`
- `windows_verify`
- `secureboot_enroll`
- `bitlocker_unlock` with an allowlisted `/dev` device and key on stdin

The Tauri bridge validates the same operation and payload allowlist, submits
the request on a worker thread, and exposes a job status to the frontend.
Successful and failed operations are recorded in
`/var/log/kyth/privileged.log`; BitLocker keys are never recorded.

The service is installed by the image branding step and is not expected to be
available in an uninstalled source checkout.
