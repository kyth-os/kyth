//! Per-display HDR configuration and EDID luminance parsing.

use std::collections::BTreeMap;
use std::path::Path;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct HdrDisplay {
    pub peak_nits: i64,
    pub hdr_enabled: bool,
    pub sdr_nits: i64,
}

impl Default for HdrDisplay {
    fn default() -> Self { Self { peak_nits: 400, hdr_enabled: false, sdr_nits: 200 } }
}

fn clamp(display: HdrDisplay) -> HdrDisplay {
    HdrDisplay { peak_nits: display.peak_nits.clamp(100, 4_000), hdr_enabled: display.hdr_enabled, sdr_nits: display.sdr_nits.clamp(80, 600) }
}

pub fn load(path: impl AsRef<Path>) -> BTreeMap<String, HdrDisplay> {
    let Ok(raw) = std::fs::read_to_string(path) else { return BTreeMap::new(); };
    let Ok(value) = raw.parse::<toml::Value>() else { return BTreeMap::new(); };
    value.get("displays").and_then(toml::Value::as_table).map(|displays| displays.iter().filter_map(|(name, value)| {
        let entry = value.as_table()?;
        Some((name.clone(), clamp(HdrDisplay {
            peak_nits: entry.get("peak_nits").and_then(toml::Value::as_integer).unwrap_or(400),
            hdr_enabled: entry.get("hdr_enabled").and_then(toml::Value::as_bool).unwrap_or(false),
            sdr_nits: entry.get("sdr_nits").and_then(toml::Value::as_integer).unwrap_or(200),
        })))
    }).collect()).unwrap_or_default()
}

pub fn save(path: impl AsRef<Path>, displays: &BTreeMap<String, HdrDisplay>) -> std::io::Result<()> {
    let mut text = String::from("# Kyth per-display HDR mastering — EDID + KWin\n");
    for (name, display) in displays {
        let display = clamp(display.clone());
        text.push_str(&format!("[displays.{name:?}]\npeak_nits = {}\nhdr_enabled = {}\nsdr_nits = {}\n\n", display.peak_nits, display.hdr_enabled, display.sdr_nits));
    }
    crate::atomic_io::atomic_write_text(path, &text, Some(0o600))
}

pub fn parse_edid_peak_nits(data: &[u8]) -> Option<i64> {
    if data.len() < 128 { return None; }
    let extension_count = data[126];
    if extension_count == 0 || data.len() < 256 { return None; }
    data.iter().enumerate().skip(128).take(384).find_map(|(index, byte)| {
        let value = *byte;
        let maybe_peak = *data.get(index + 2)?;
        (value == 0x06 && (1..=10).contains(&maybe_peak)).then_some(i64::from(maybe_peak) * 100)
    })
}

pub fn env_hints(display: &HdrDisplay) -> BTreeMap<String, String> {
    let display = clamp(display.clone());
    if !display.hdr_enabled { return BTreeMap::new(); }
    BTreeMap::from([
        ("KYTH_HDR".into(), "1".into()),
        ("KYTH_HDR_PEAK_NITS".into(), display.peak_nits.to_string()),
        ("KYTH_HDR_SDR_NITS".into(), display.sdr_nits.to_string()),
    ])
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::tempdir;

    #[test]
    fn clamps_and_round_trips_display_config() {
        let directory = tempdir().unwrap();
        let path = directory.path().join("display-hdr.toml");
        let mut displays = BTreeMap::new();
        displays.insert("HDMI-1".into(), HdrDisplay { peak_nits: 10, hdr_enabled: true, sdr_nits: 999 });
        save(&path, &displays).unwrap();
        assert_eq!(load(&path)["HDMI-1"], HdrDisplay { peak_nits: 100, hdr_enabled: true, sdr_nits: 600 });
        assert_eq!(env_hints(&load(&path)["HDMI-1"]).get("KYTH_HDR"), Some(&"1".into()));
    }

    #[test]
    fn finds_extension_block_peak_hint() {
        let mut edid = vec![0_u8; 256];
        edid[126] = 1;
        edid[128] = 0x06;
        edid[130] = 4;
        assert_eq!(parse_edid_peak_nits(&edid), Some(400));
        assert_eq!(parse_edid_peak_nits(&edid[..127]), None);
    }
}
