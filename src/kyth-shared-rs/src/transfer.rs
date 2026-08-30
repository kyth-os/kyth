//! Small, dependency-free transfer and byte-formatting helpers.
//!
//! These mirror the shared installer/welcome helpers.  They intentionally do
//! not own network polling or UI state; callers can use the deterministic
//! formatters from native Rust surfaces without crossing into Python.

use std::collections::VecDeque;

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

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct TransferProgress { pub downloaded: u64, pub total: u64, pub speed: u64, pub eta_sec: u64 }

/// Pure rolling transfer model matching Python's `NetStatsTracker`.
pub struct NetStatsTracker { total: u64, rx_start: u64, rx_prev: u64, time_prev: f64, samples: VecDeque<f64> }

impl NetStatsTracker {
    pub fn new(total: u64, rx_start: u64, time_start: f64) -> Self { Self { total, rx_start, rx_prev: 0, time_prev: time_start, samples: VecDeque::with_capacity(5) } }
    pub fn tick_at(&mut self, rx_now: u64, time_now: f64) -> TransferProgress {
        let downloaded = rx_now.saturating_sub(self.rx_start).min(self.total);
        let dt = time_now - self.time_prev;
        if dt > 0.0 && self.rx_prev > 0 { let delta = rx_now.saturating_sub(self.rx_prev); if delta > 0 { if self.samples.len() == 5 { self.samples.pop_front(); } self.samples.push_back(delta as f64 / dt); } }
        self.rx_prev = rx_now; self.time_prev = time_now;
        let speed = if self.samples.is_empty() { 0 } else { (self.samples.iter().sum::<f64>() / self.samples.len() as f64) as u64 };
        TransferProgress { downloaded, total: self.total, speed, eta_sec: if speed == 0 { 0 } else { self.total.saturating_sub(downloaded) / speed } }
    }
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

    #[test]
    fn tracks_rolling_transfer_rate_without_polling() {
        let mut tracker = NetStatsTracker::new(1_000, 100, 0.0);
        assert_eq!(tracker.tick_at(100, 1.0).speed, 0);
        let progress = tracker.tick_at(300, 3.0);
        assert_eq!(progress.downloaded, 200);
        assert_eq!(progress.speed, 100);
        assert_eq!(progress.eta_sec, 8);
    }
}
