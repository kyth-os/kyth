//! Port of `kyth_shared.system.registry` — skopeo/OCI helpers.

use std::collections::HashMap;
use serde_json::Value;

#[derive(Debug, Clone)]
pub struct UpdateCheckResult {
    pub state: String,
    pub detail: String,
    pub manifest_raw: Vec<u8>,
}

pub fn booted_image_digest(status_data: &Value) -> Option<String> {
    crate::system::bootc_query::image_digest_from_status(status_data).map(|(_, full)| full)
}

pub fn amd64_manifest_entry(manifest: &Value) -> Option<Value> {
    let manifests = manifest.get("manifests")?.as_array()?;
    for entry in manifests {
        let plat = entry.get("platform")?;
        if plat.get("architecture")?.as_str() == Some("amd64") && plat.get("os")?.as_str() == Some("linux") {
            return Some(entry.clone());
        }
    }
    None
}

pub fn image_annotations(manifest: &Value) -> HashMap<String, String> {
    let mut ann: HashMap<String,String> = manifest.get("annotations").and_then(|v| v.as_object()).map(|m| m.iter().filter_map(|(k,v)| v.as_str().map(|s| (k.clone(), s.to_string()))).collect()).unwrap_or_default();
    if !ann.contains_key("org.opencontainers.image.revision") {
        if let Some(entry) = amd64_manifest_entry(manifest) {
            if let Some(eann) = entry.get("annotations").and_then(|v| v.as_object()) {
                for (k,v) in eann { if let Some(s)=v.as_str() { ann.insert(k.clone(), s.to_string()); } }
            }
        }
    }
    ann
}

pub fn image_revision(ann: &HashMap<String,String>) -> String {
    ann.get("org.opencontainers.image.revision").map(|s| s.chars().take(12).collect()).unwrap_or_default()
}

pub fn remote_digest_and_timestamp(raw: &[u8]) -> (Option<String>, String) {
    let manifest: Value = serde_json::from_slice(raw).unwrap_or(Value::Null);
    let mut ts = String::new();
    if let Some(ann) = manifest.get("annotations").and_then(|v| v.as_object()) {
        if let Some(raw_ts) = ann.get("org.opencontainers.image.created").and_then(|v| v.as_str()) {
            ts = raw_ts.to_string();
        }
    }
    let digest = if manifest.get("mediaType").and_then(|v| v.as_str()).map(|s| s.ends_with("manifest.v1+json")).unwrap_or(false) {
        Some("sha256:dummy".to_string())
    } else if manifest.get("manifests").and_then(|v| v.as_array()).is_some() {
        amd64_manifest_entry(&manifest).and_then(|e| e.get("digest").and_then(|v| v.as_str()).map(|s| s.to_string())).filter(|s| s.starts_with("sha256:"))
    } else if manifest.get("config").is_some() && manifest.get("layers").is_some() {
        Some("sha256:dummy".to_string())
    } else { None };
    (digest, ts)
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;
    #[test]
    fn amd64() {
        let m = json!({"manifests":[{"platform":{"architecture":"amd64","os":"linux"},"digest":"sha256:abc"}]});
        assert!(amd64_manifest_entry(&m).is_some());
    }
    #[test]
    fn revision() {
        let mut ann = HashMap::new();
        ann.insert("org.opencontainers.image.revision".to_string(), "abcdef1234567890".to_string());
        assert_eq!(image_revision(&ann), "abcdef123456");
    }
}
