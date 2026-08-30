//! Small, dependency-free transfer and byte-formatting helpers.
//!
//! These mirror the shared installer/welcome helpers.  They intentionally do
//! not own network polling or UI state; callers can use the deterministic
//! formatters from native Rust surfaces without crossing into Python.

pub fn parse_size_bytes(size: &str) -> u64 {
    let mut parts = size.split_whitespace();
    let Some(value) = parts.next().and_then(|value| value.parse::<f64>().ok()) else {
        return 0;
    };
    let unit = parts.next().unwrap_or_default().to_ascii_uppercase().trim_end_matches('B').replace('I', "");
    let multiplier = match unit.as_str() {
        "" => 1_u64,
        "K" => 1024,
        "M" => 1024_u64.pow(2),
        "G" => 1024_u64.pow(3),
        "T" => 1024_u64.pow(4),
        _ => return 0,
    } as f64;
    if !value.is_finite() || value < 0.0 {
        return 0;
    }
    (value * multiplier) as u64
}

pub fn human_bytes(bytes: f64) -> String {
    if bytes < 1024.0 {
        return format_number(bytes, 0, "B");
    }
    let mut value = bytes;
    for unit in ["KB", "MB", "GB"] {
        value /= 1024.0;
        if value < 1024.0 {
            return format_number(value, 1, unit);
        }
    }
    format_number(value / 1024.0, 1, "TB")
}

fn format_number(value: f64, decimals: usize, unit: &str) -> String {
    if decimals == 0 {
        format!("{} {unit}", value as i64)
    } else {
        format!("{value:.decimals$} {unit}")
    }
}

pub fn human_bytes_pair(downloaded: u64, total: u64) -> (String, String) {
    for (unit, threshold) in [("GB", 1024_u64.pow(3)), ("MB", 1024_u64.pow(2)), ("KB", 1024)] {
        if total >= threshold {
            return (format!("{:.1}", downloaded as f64 / threshold as f64), format!("{:.1} {unit}", total as f64 / threshold as f64));
        }
    }
    (downloaded.to_string(), format!("{total} B"))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_iec_and_rejects_invalid_sizes() {
        assert_eq!(parse_size_bytes("8.3 GB"), (8.3_f64 * 1024_u64.pow(3) as f64) as u64);
        assert_eq!(parse_size_bytes("2 GiB"), 2 * 1024_u64.pow(3));
        assert_eq!(parse_size_bytes("not a size"), 0);
        assert_eq!(parse_size_bytes("-1 GB"), 0);
    }

    #[test]
    fn formats_bytes_and_download_pairs() {
        assert_eq!(human_bytes(1024.0), "1.0 KB");
        assert_eq!(human_bytes(1.0), "1 B");
        assert_eq!(human_bytes_pair(1_400_000, 1_500_000), ("1.3".into(), "1.4 MB".into()));
        assert_eq!(human_bytes_pair(10, 12), ("10".into(), "12 B".into()));
    }
}
