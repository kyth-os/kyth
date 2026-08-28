//! Current-user identity for the Hub's greeting — no Python original.
//!
//! The Qt Hub never greeted by name; the React dashboard shipped a
//! hardcoded `name="Mark"`, so every user was greeted as someone else.
//! Read-only and cheap (one env read, one /etc/passwd parse), which is
//! what MIGRATION.md permits in this crate.

use std::fs;

/// GECOS field 1 is the human name, comma-separated from office/phone
/// fields. Empty or `*`-only entries are treated as absent rather than
/// rendered literally.
fn gecos_full_name(passwd_line: &str) -> Option<String> {
    let gecos = passwd_line.split(':').nth(4)?;
    let name = gecos.split(',').next().unwrap_or("").trim();
    if name.is_empty() || name == "*" {
        None
    } else {
        Some(name.to_string())
    }
}

/// Pure half of [`current_user_display_name`] so the parse is testable
/// without depending on whoever happens to be running the tests.
pub fn display_name_from_passwd(passwd: &str, username: &str) -> Option<String> {
    if username.is_empty() {
        return None;
    }
    for line in passwd.lines() {
        if line.split(':').next() == Some(username) {
            return gecos_full_name(line);
        }
    }
    None
}

fn current_username() -> String {
    for key in ["USER", "LOGNAME"] {
        if let Ok(value) = std::env::var(key) {
            let value = value.trim().to_string();
            if !value.is_empty() {
                return value;
            }
        }
    }
    String::new()
}

/// Human name for the greeting: GECOS full name when set, otherwise the
/// login name, otherwise empty — callers render a name-less greeting on
/// empty rather than inventing one.
pub fn current_user_display_name() -> String {
    let username = current_username();
    if username.is_empty() {
        return String::new();
    }
    let passwd = fs::read_to_string("/etc/passwd").unwrap_or_default();
    display_name_from_passwd(&passwd, &username).unwrap_or(username)
}

#[cfg(test)]
mod tests {
    use super::*;

    const PASSWD: &str = "root:x:0:0:root:/root:/bin/bash\n\
phendrick:x:1000:1000:Pat Hendrick,,,:/var/home/phendrick:/bin/bash\n\
nogecos:x:1001:1001::/home/nogecos:/bin/bash\n\
starred:x:1002:1002:*:/home/starred:/bin/bash\n";

    #[test]
    fn prefers_gecos_full_name() {
        assert_eq!(
            display_name_from_passwd(PASSWD, "phendrick"),
            Some("Pat Hendrick".to_string())
        );
    }

    #[test]
    fn empty_gecos_is_absent_not_blank() {
        assert_eq!(display_name_from_passwd(PASSWD, "nogecos"), None);
    }

    #[test]
    fn placeholder_gecos_is_not_rendered() {
        assert_eq!(display_name_from_passwd(PASSWD, "starred"), None);
    }

    #[test]
    fn unknown_user_has_no_name() {
        assert_eq!(display_name_from_passwd(PASSWD, "absent"), None);
    }

    #[test]
    fn empty_username_never_matches() {
        assert_eq!(display_name_from_passwd(PASSWD, ""), None);
    }

    #[test]
    fn does_not_confuse_username_with_other_fields() {
        // "x" appears as the password field on every line; a substring or
        // wrong-field match would wrongly resolve it to a real user.
        assert_eq!(display_name_from_passwd(PASSWD, "x"), None);
    }

    #[test]
    fn real_read_never_panics() {
        let _ = current_user_display_name();
    }
}
