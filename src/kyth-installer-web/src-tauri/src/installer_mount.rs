//! Pure mount-lifecycle state for the installer shell.
//!
//! This mirrors Python's LIFO mount registry without performing mount or
//! unmount operations. The privileged service remains responsible for those
//! commands and for reporting failures; Rust only tracks cleanup order.

#[derive(Debug, Default, PartialEq, Eq)]
pub(crate) struct MountRegistry {
    stack: Vec<String>,
}

impl MountRegistry {
    pub(crate) fn register(&mut self, path: impl Into<String>) {
        let path = path.into();
        if !self.stack.contains(&path) {
            self.stack.push(path);
        }
    }

    pub(crate) fn release(&mut self, path: &str) {
        if let Some(index) = self.stack.iter().rposition(|entry| entry == path) {
            self.stack.remove(index);
        }
    }

    pub(crate) fn snapshot(&self) -> Vec<String> {
        self.stack.clone()
    }

    pub(crate) fn clear(&mut self) {
        self.stack.clear();
    }

    /// Return the cleanup order and clear the registry even if an executor
    /// later reports an unmount failure for one of the returned paths.
    pub(crate) fn cleanup_order(&mut self) -> Vec<String> {
        let mut order = self.snapshot();
        order.reverse();
        self.clear();
        order
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::Value;

    #[test]
    fn register_is_idempotent_and_release_removes_the_topmost_match() {
        let mut registry = MountRegistry::default();
        registry.register("/target");
        registry.register("/target/home");
        registry.register("/target");
        assert_eq!(registry.snapshot(), vec!["/target", "/target/home"]);
        registry.release("/target");
        assert_eq!(registry.snapshot(), vec!["/target/home"]);
    }

    #[test]
    fn cleanup_is_lifo_and_clears_state() {
        let mut registry = MountRegistry::default();
        registry.register("/target");
        registry.register("/target/boot");
        assert_eq!(registry.cleanup_order(), vec!["/target/boot", "/target"]);
        assert!(registry.snapshot().is_empty());
    }

    #[test]
    fn shared_mount_fixture_matches_registry_state() {
        let cases: Vec<Value> = serde_json::from_str(include_str!("../testdata/mount_cases.json"))
            .expect("mount parity fixture must be valid JSON");
        for case in cases {
            let name = case["name"].as_str().expect("fixture case needs a name");
            let mut registry = MountRegistry::default();
            for operation in case["operations"].as_array().expect("operations are an array") {
                match operation["action"].as_str().expect("operation action is a string") {
                    "register" => registry.register(operation["path"].as_str().unwrap()),
                    "release" => registry.release(operation["path"].as_str().unwrap()),
                    "clear" => registry.clear(),
                    action => panic!("{name}: unsupported action {action}"),
                }
            }
            let expected_snapshot: Vec<String> = serde_json::from_value(case["expected_snapshot"].clone())
                .expect("expected snapshot is a string array");
            let expected_cleanup: Vec<String> = serde_json::from_value(case["expected_cleanup"].clone())
                .expect("expected cleanup is a string array");
            assert_eq!(registry.snapshot(), expected_snapshot, "{name}: snapshot");
            assert_eq!(registry.cleanup_order(), expected_cleanup, "{name}: cleanup");
            assert!(registry.snapshot().is_empty(), "{name}: cleanup must clear state");
        }
    }
}
