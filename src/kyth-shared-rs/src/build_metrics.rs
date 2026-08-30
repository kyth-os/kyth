//! Deterministic static metrics used by the optimization report.
//!
//! Filesystem traversal and runtime probe execution remain in the build
//! script. These helpers keep metric calculation and report shape reusable.

use serde::Serialize;
use serde_json::{json, Value};

#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize)]
pub struct StaticMetrics {
    pub installer_js_max_file_bytes: u64,
    pub probe_collector_count: u64,
    pub system_hub_inline_styles: u64,
    pub system_hub_python_modules: u64,
}

pub fn max_file_size(sizes: impl IntoIterator<Item = u64>) -> u64 {
    sizes.into_iter().max().unwrap_or(0)
}

/// Count `ProbeCollector(` entries in the default collector block, matching
/// the build script's deliberately simple source-level metric.
pub fn probe_collector_count(source: &str) -> u64 {
    let Some((_, remainder)) = source.split_once("def default_collectors()") else { return 0; };
    let body = remainder.split_once("def _run_collector").map_or(remainder, |(body, _)| body);
    body.matches("ProbeCollector(").count() as u64
}

pub fn static_metrics(
    installer_js_sizes: impl IntoIterator<Item = u64>,
    probe_source: &str,
    inline_style_count: u64,
    python_module_count: u64,
) -> StaticMetrics {
    StaticMetrics {
        installer_js_max_file_bytes: max_file_size(installer_js_sizes),
        probe_collector_count: probe_collector_count(probe_source),
        system_hub_inline_styles: inline_style_count,
        system_hub_python_modules: python_module_count,
    }
}

pub fn report(source_revision: &str, static_metrics: &StaticMetrics, budgets: &Value, artifacts: &Value) -> Value {
    json!({
        "schema_version": 1,
        "source_revision": source_revision,
        "static": static_metrics,
        "budgets": budgets,
        "artifacts": artifacts,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn counts_only_the_default_collector_block() {
        let source = "def default_collectors():\n  ProbeCollector(a)\n  ProbeCollector(b)\ndef _run_collector(x):\n  ProbeCollector(c)\n";
        assert_eq!(probe_collector_count(source), 2);
        assert_eq!(probe_collector_count("no collector function"), 0);
    }

    #[test]
    fn static_report_has_optimization_contract_shape() {
        let metrics = static_metrics([4, 9, 2], "def default_collectors(): ProbeCollector(x)", 3, 8);
        assert_eq!(metrics.installer_js_max_file_bytes, 9);
        let value = report("local", &metrics, &json!({"x": 10}), &json!({}));
        assert_eq!(value["schema_version"], 1);
        assert_eq!(value["static"]["probe_collector_count"], 1);
        assert_eq!(value["source_revision"], "local");
    }
}
