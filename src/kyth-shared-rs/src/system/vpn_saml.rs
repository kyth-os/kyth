//! Pure command projection for the VPN SAML sleep-survival helper.

pub const SLEEP_SURVIVE: bool = true;

/// Return the TERM-then-KILL cascade used by the bounded VPN worker.
pub fn kill_cascade(pid: u32) -> Vec<Vec<String>> {
    ["TERM", "KILL"]
        .into_iter()
        .map(|signal| vec!["kill".into(), format!("-{signal}"), pid.to_string()])
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn cascade_is_ordered_and_sleep_survival_is_enabled() {
        assert!(SLEEP_SURVIVE);
        assert_eq!(kill_cascade(42), vec![
            vec!["kill", "-TERM", "42"],
            vec!["kill", "-KILL", "42"],
        ]);
    }
}
