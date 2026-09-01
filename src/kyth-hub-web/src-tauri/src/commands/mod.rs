//! Tauri command domains.
//!
//! Keep command implementations grouped by the UI workflow they serve. The
//! public names in these modules are the stable IPC contract; moving a
//! command between modules must not change its Tauri command name.

pub(crate) mod dashboard;
pub(crate) mod privilege;
pub(crate) mod process;
pub(crate) mod security;
pub(crate) mod updates;
