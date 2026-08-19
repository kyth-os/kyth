"""Service helpers for System Hub pages.

Service modules keep command construction, parsing, and result shaping out of
Qt widget classes so pages can focus on rendering state.

Layering:
  process            — subprocess helpers + probe cache (no Qt)
  bootc              — bootc status / branch / deployment (no Qt)
  registry           — skopeo/registry digest checks (no Qt)
  runtime            — shared Qt worker threads
  phone_link         — KDE Connect + Dynamic Lock
  windows_migration/ — BitLocker, bookmarks, saves, extras, HW sanity
  hardware/          — probe types + GPU/display/IO/system/codec collectors
  gaming/            — tools, steam, health, protondb, compat, partitions
  repair             — setup-transfer / snapshot / bootc reset command builders
  sched / telem      — kyth-sched status + MangoHud session history
  *                  — domain services (software, network, updates, vpn, cloud_sync, …)
"""
