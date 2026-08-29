//! Read-only decoder for the installer transaction-state schema.
//!
//! Python still owns atomic writes and file permissions. This module only
//! decodes the support-safe JSON record and attaches the already-parity-tested
//! Rescue guidance.

use serde::{Deserialize, Serialize};
use serde_json::Value;

use crate::installer_recovery::{rescue_guidance, RecoveryGuidance};

fn default_schema_version() -> u32 { 1 }

#[derive(Clone, Debug, Default, Deserialize, PartialEq, Serialize)]
pub(crate) struct TransactionSource {
    #[serde(default)]
    pub kind: String,
    #[serde(default)]
    pub digest: String,
    #[serde(default)]
    pub verified: bool,
    #[serde(default)]
    pub target_ref: String,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
pub(crate) struct TransactionState {
    #[serde(default = "default_schema_version")]
    pub schema_version: u32,
    #[serde(default)]
    pub transaction_id: String,
    #[serde(default)]
    pub updated_at: String,
    #[serde(default)]
    pub status: String,
    #[serde(default)]
    pub phase: String,
    #[serde(default)]
    pub lifecycle: String,
    #[serde(default)]
    pub install_mode: String,
    #[serde(default)]
    pub disk: String,
    #[serde(default)]
    pub target_partition: String,
    #[serde(default)]
    pub source: TransactionSource,
    #[serde(default)]
    pub checks: Vec<Value>,
    #[serde(default)]
    pub partition_steps: Vec<Value>,
    #[serde(default)]
    pub message: String,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
pub(crate) struct DecodedTransaction {
    pub state: TransactionState,
    pub guidance: RecoveryGuidance,
}

pub(crate) fn decode(input: &str) -> Result<DecodedTransaction, String> {
    let state: TransactionState = serde_json::from_str(input)
        .map_err(|error| format!("invalid transaction state: {error}"))?;
    if state.schema_version != 1 {
        return Err(format!("unsupported transaction state schema: {}", state.schema_version));
    }
    let guidance = rescue_guidance(Some(&state.status));
    Ok(DecodedTransaction { state, guidance })
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::Value;

    #[test]
    fn shared_transaction_fixture_decodes_and_classifies() {
        let cases: Vec<Value> = serde_json::from_str(include_str!("../testdata/transaction_cases.json"))
            .expect("transaction parity fixture must be valid JSON");
        for case in cases {
            let name = case["name"].as_str().expect("fixture case needs a name");
            if case.get("error_contains").is_some() {
                let error = decode(&case["json"].to_string()).expect_err("invalid state must fail");
                assert!(error.contains(case["error_contains"].as_str().unwrap()), "{name}: {error}");
                continue;
            }
            let decoded = decode(&case["json"].to_string()).unwrap_or_else(|error| panic!("{name}: {error}"));
            assert_eq!(decoded.state.status, case["expected"]["status"].as_str().unwrap(), "{name}");
            assert_eq!(decoded.state.phase, case["expected"]["phase"].as_str().unwrap(), "{name}");
            assert_eq!(decoded.state.disk, case["expected"]["disk"].as_str().unwrap(), "{name}");
            assert_eq!(decoded.state.source.digest, case["expected"]["source_digest"].as_str().unwrap(), "{name}");
            assert_eq!(decoded.guidance.severity, case["expected"]["severity"].as_str().unwrap(), "{name}");
            assert_eq!(decoded.guidance.bootable, case["expected"]["bootable"].as_bool().unwrap(), "{name}");
        }
    }
}
