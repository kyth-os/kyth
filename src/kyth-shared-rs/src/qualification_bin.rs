//! Native qualification report and regression-gate CLI.

use std::env;
use std::fs;
use std::path::{Path, PathBuf};
use std::process::ExitCode;
use std::time::{SystemTime, UNIX_EPOCH};

use kyth_shared::atomic_io::atomic_write_text;
use kyth_shared::system::qualification::{
    acceptance_report, evaluate_regressions, QualificationReport, RegressionBudget, SCHEMA_VERSION,
};

fn generated_at() -> String {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|value| value.as_secs().to_string())
        .unwrap_or_else(|_| "0".into())
}

fn read_report(path: &Path) -> Result<QualificationReport, String> {
    let text = fs::read_to_string(path)
        .map_err(|error| format!("could not read {}: {error}", path.display()))?;
    serde_json::from_str(&text)
        .map_err(|error| format!("could not parse {}: {error}", path.display()))
}

fn write_report(
    report: &QualificationReport,
    output: &Path,
    markdown: Option<&Path>,
) -> Result<(), String> {
    atomic_write_text(output, &report.to_json(), Some(0o644))
        .map_err(|error| format!("could not write {}: {error}", output.display()))?;
    if let Some(markdown) = markdown {
        atomic_write_text(markdown, &report.to_markdown(), Some(0o644))
            .map_err(|error| format!("could not write {}: {error}", markdown.display()))?;
    }
    Ok(())
}

fn option(args: &mut Vec<String>, name: &str) -> Option<PathBuf> {
    let index = args.iter().position(|value| value == name)?;
    args.remove(index);
    (index < args.len()).then(|| PathBuf::from(args.remove(index)))
}

fn usage() {
    eprintln!(
        "usage: kyth-qualify acceptance --log PATH --output PATH [--markdown PATH] [--update-required]\n\
         kyth-qualify gate --candidate PATH --baseline PATH --budgets PATH [--output PATH] [--markdown PATH]"
    );
}

fn run(args: &mut Vec<String>) -> Result<QualificationReport, String> {
    let command = args.first().cloned().unwrap_or_default();
    match command.as_str() {
        "acceptance" => {
            let log = option(args, "--log").ok_or("acceptance requires --log")?;
            let output = option(args, "--output").ok_or("acceptance requires --output")?;
            let markdown = option(args, "--markdown");
            let update_required = args.iter().any(|value| value == "--update-required");
            let content = fs::read_to_string(&log)
                .map_err(|error| format!("could not read {}: {error}", log.display()))?;
            let report = acceptance_report(&content, update_required, generated_at());
            write_report(&report, &output, markdown.as_deref())?;
            Ok(report)
        }
        "gate" => {
            let candidate_path = option(args, "--candidate").ok_or("gate requires --candidate")?;
            let baseline_path = option(args, "--baseline").ok_or("gate requires --baseline")?;
            let budgets_path = option(args, "--budgets").ok_or("gate requires --budgets")?;
            let output = option(args, "--output").unwrap_or_else(|| candidate_path.clone());
            let markdown = option(args, "--markdown");
            let candidate = read_report(&candidate_path)?;
            let baseline = read_report(&baseline_path)?;
            let budgets_text = fs::read_to_string(&budgets_path)
                .map_err(|error| format!("could not read {}: {error}", budgets_path.display()))?;
            let budgets_value: serde_json::Value = serde_json::from_str(&budgets_text)
                .map_err(|error| format!("could not parse {}: {error}", budgets_path.display()))?;
            if budgets_value
                .get("schema_version")
                .and_then(serde_json::Value::as_u64)
                != Some(SCHEMA_VERSION as u64)
            {
                return Err("unsupported regression budget schema version".into());
            }
            let budgets = parse_budgets(&budgets_value)?;
            let report = evaluate_regressions(candidate, &baseline, &budgets);
            write_report(&report, &output, markdown.as_deref())?;
            Ok(report)
        }
        _ => Err("unknown qualification command".into()),
    }
}

/// A gate with no budgets can gate nothing, so a missing, non-array or empty
/// `budgets` list is an error. It used to default to `[]`, which turned a typo
/// such as `"budget"` into `overall: pass` for any regression.
fn parse_budgets(value: &serde_json::Value) -> Result<Vec<RegressionBudget>, String> {
    let list = value
        .get("budgets")
        .ok_or("budgets file has no \"budgets\" list (misspelled key?)")?;
    if !list.is_array() {
        return Err("\"budgets\" must be a list".into());
    }
    let budgets: Vec<RegressionBudget> = serde_json::from_value(list.clone())
        .map_err(|error| format!("invalid regression budgets: {error}"))?;
    if budgets.is_empty() {
        return Err("budgets file defines no budgets, so nothing would be gated".into());
    }
    Ok(budgets)
}

fn main() -> ExitCode {
    let mut args: Vec<String> = env::args().skip(1).collect();
    if args.iter().any(|value| value == "--help" || value == "-h") {
        usage();
        return ExitCode::SUCCESS;
    }
    match run(&mut args) {
        Ok(report) => {
            println!("{}", report.to_json());
            if report.overall() == "fail" {
                ExitCode::from(1)
            } else {
                ExitCode::SUCCESS
            }
        }
        Err(error) => {
            eprintln!("kyth-qualify: {error}");
            usage();
            ExitCode::from(2)
        }
    }
}

#[cfg(test)]
mod tests {
    use super::parse_budgets;
    use serde_json::json;

    #[test]
    fn a_budgets_file_that_gates_nothing_is_refused() {
        // Misspelled key, wrong type and empty list all used to become "no
        // budgets" and let a 90% fps regression pass.
        for bad in [
            json!({"schema_version": 1, "budget": [{"metric": "fps", "max_regression_percent": 5.0}]}),
            json!({"schema_version": 1}),
            json!({"schema_version": 1, "budgets": {}}),
            json!({"schema_version": 1, "budgets": []}),
        ] {
            assert!(parse_budgets(&bad).is_err(), "{bad} must be refused");
        }
        let good = json!({"schema_version": 1, "budgets": [{"metric": "fps", "max_regression_percent": 5.0}]});
        assert_eq!(parse_budgets(&good).unwrap().len(), 1);
    }
}
