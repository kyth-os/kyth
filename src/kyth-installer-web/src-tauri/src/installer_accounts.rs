//! Bounded offline installer-account creation.
//!
//! The password hash is accepted only in the operation body (stdin) and is
//! never placed in argv, logs, or a diagnostic response.

use std::fs::{self, OpenOptions};
use std::io::Write;
use std::os::unix::fs::{OpenOptionsExt, PermissionsExt};
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};

/// Shared installer contract (`validation_rules.json`): `[a-z_][a-z0-9_-]{0,30}`.
/// Accepting uppercase or a leading digit here let a request pass validation
/// and then fail at `useradd` after the image was already written.
const MAX_USERNAME: usize = 31;

fn valid_username(username: &str) -> bool {
    let bytes = username.as_bytes();
    !bytes.is_empty()
        && bytes.len() <= MAX_USERNAME
        && (bytes[0].is_ascii_lowercase() || bytes[0] == b'_')
        && bytes[1..]
            .iter()
            .all(|b| b.is_ascii_lowercase() || b.is_ascii_digit() || matches!(b, b'_' | b'-'))
}

#[derive(Clone, Debug, serde::Deserialize, serde::Serialize)]
pub struct CreateUserInput {
    pub deploy_root: String,
    pub target_root: String,
    pub username: String,
    pub password_hash: String,
}

/// Hash a frontend password without placing it in argv, logs, or a durable
/// request object. The native daemon consumes plaintext only long enough to
/// feed the fixed SHA-512 crypt operation through stdin.
pub(crate) fn hash_password(password: &str) -> Result<String, String> {
    if password.is_empty() {
        return Err(
            "Password cannot be empty. Return to the Configure step and re-enter it.".into(),
        );
    }
    if password.contains('\0') {
        return Err("Password contains an unsupported character".into());
    }
    if password.contains(['\n', '\r']) {
        return Err("Password cannot contain a line break".into());
    }
    let mut child = Command::new("/usr/bin/openssl")
        .args(["passwd", "-6", "-stdin"])
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::null())
        .spawn()
        .map_err(|error| format!("could not hash password: {error}"))?;
    if let Some(mut stdin) = child.stdin.take() {
        if let Err(error) = stdin.write_all(password.as_bytes()) {
            let _ = child.kill();
            let _ = child.wait();
            return Err(format!("could not provide password to hasher: {error}"));
        }
    }
    let output = child
        .wait_with_output()
        .map_err(|error| format!("could not wait for password hasher: {error}"))?;
    if !output.status.success() {
        return Err("password hashing failed".into());
    }
    let hash = String::from_utf8(output.stdout)
        .map_err(|_| "password hashing returned non-UTF-8 output".to_string())?;
    let hash = hash.trim();
    if !hash.starts_with("$6$") || hash.contains(['\n', '\r', '\0']) {
        return Err("password hashing returned an invalid SHA-512 crypt value".into());
    }
    Ok(hash.to_string())
}

fn absolute_tree(value: &str, label: &str) -> Result<PathBuf, String> {
    let path = PathBuf::from(value);
    if !path.is_absolute()
        || path
            .components()
            .any(|part| matches!(part, std::path::Component::ParentDir))
    {
        return Err(format!(
            "{label} must be an absolute path without parent traversal"
        ));
    }
    Ok(path)
}

pub fn validate(input: &CreateUserInput) -> Result<(PathBuf, PathBuf), String> {
    let deploy = absolute_tree(&input.deploy_root, "deploy_root")?;
    let target = absolute_tree(&input.target_root, "target_root")?;
    let username = input.username.trim();
    if !valid_username(username) {
        return Err(
            "username must start with a lowercase letter or underscore and use only lowercase letters, digits, '_' or '-' (at most 31 characters)"
                .into(),
        );
    }
    if input.password_hash.is_empty() || input.password_hash.contains(['\n', '\r', '\0', ':']) {
        return Err("password_hash must be a single non-empty line without ':'".into());
    }
    Ok((deploy, target))
}

fn run(program: &str, args: &[&str]) -> Result<(), String> {
    let status = Command::new(program)
        .args(args)
        .status()
        .map_err(|e| format!("could not run {program}: {e}"))?;
    if status.success() {
        Ok(())
    } else {
        Err(format!("{program} failed"))
    }
}

/// Properties `apply` sets via `useradd`. When the user already exists in the
/// installed system, these must match; anything else fails closed instead of
/// silently adopting or modifying a foreign account.
const EXPECTED_SHELL: &str = "/bin/bash";
const EXPECTED_GROUPS: &[&str] = &["wheel", "video", "audio", "render"];

/// True when `username` already has an entry in the installed system's
/// passwd database. This checks the *target* root (`--root` semantics), not
/// the live session: `id <name>` would answer for the wrong system.
fn target_user_exists(passwd_path: &Path, username: &str) -> Result<bool, String> {
    let content = fs::read_to_string(passwd_path)
        .map_err(|e| format!("could not read installed passwd: {e}"))?;
    Ok(content.lines().any(|line| {
        line.split_once(':')
            .is_some_and(|(name, _)| name == username)
    }))
}

/// Verify an already-existing target user matches the properties `apply`
/// would set (login shell and supplementary groups). A foreign account with
/// the same name must never be silently adopted.
fn verify_matching_properties(etc: &Path, username: &str) -> Result<(), String> {
    let passwd = fs::read_to_string(etc.join("passwd"))
        .map_err(|e| format!("could not read installed passwd: {e}"))?;
    let entry = passwd
        .lines()
        .find_map(|line| {
            let fields: Vec<_> = line.split(':').collect();
            (fields.first() == Some(&username)).then_some(fields)
        })
        .ok_or_else(|| format!("user {username:?} disappeared from installed passwd"))?;
    let shell = entry.get(6).copied().unwrap_or_default();
    if shell != EXPECTED_SHELL {
        return Err(format!(
            "user {username:?} already exists in the installed system with a different login shell ({shell:?}); refusing to modify it"
        ));
    }
    let group_content = fs::read_to_string(etc.join("group"))
        .map_err(|e| format!("could not read installed group database: {e}"))?;
    for group in EXPECTED_GROUPS {
        let member = group_content.lines().any(|line| {
            let mut fields = line.split(':');
            fields.next() == Some(*group)
                && fields.nth(2).is_some_and(|members| {
                    members.split(',').any(|member| member.trim() == username)
                })
        });
        if !member {
            return Err(format!(
                "user {username:?} already exists in the installed system without the expected {group:?} group membership; refusing to modify it"
            ));
        }
    }
    Ok(())
}

fn replace_shadow_hash(path: &Path, username: &str, hash: &str) -> Result<(), String> {
    let content =
        fs::read_to_string(path).map_err(|e| format!("could not read installed shadow: {e}"))?;
    let mut found = false;
    let mut output = String::new();
    for line in content.lines() {
        if let Some((name, rest)) = line.split_once(':') {
            if name == username {
                let mut fields: Vec<&str> = rest.split(':').collect();
                if fields.is_empty() {
                    return Err("installed shadow record is malformed".into());
                }
                fields[0] = hash;
                output.push_str(name);
                output.push(':');
                output.push_str(&fields.join(":"));
                found = true;
            } else {
                output.push_str(line);
            }
        } else {
            output.push_str(line);
        }
        output.push('\n');
    }
    if !found {
        return Err(format!(
            "user {username:?} not found in the installed shadow database"
        ));
    }
    write_replacing(path, output.as_bytes())
}

/// Replace `path` atomically: write a same-directory temp file that already
/// carries the original mode, fsync it, rename it over the target, then fsync
/// the directory. A power loss leaves the old or the new shadow, never the
/// empty file that truncate-then-write could leave (a locked-out system).
fn write_replacing(path: &Path, contents: &[u8]) -> Result<(), String> {
    let mode = fs::metadata(path)
        .map_err(|e| format!("could not stat installed shadow: {e}"))?
        .permissions()
        .mode()
        & 0o7777;
    let parent = path
        .parent()
        .ok_or_else(|| "installed shadow has no parent directory".to_string())?;
    let temporary = path.with_extension("kyth-tmp");
    let _ = fs::remove_file(&temporary);
    let result = (|| {
        let mut file = OpenOptions::new()
            .write(true)
            .create_new(true)
            .mode(mode)
            .custom_flags(libc::O_NOFOLLOW)
            .open(&temporary)
            .map_err(|e| format!("could not create temporary shadow: {e}"))?;
        file.write_all(contents)
            .map_err(|e| format!("could not write temporary shadow: {e}"))?;
        file.sync_all()
            .map_err(|e| format!("could not sync temporary shadow: {e}"))?;
        fs::set_permissions(&temporary, fs::Permissions::from_mode(mode))
            .map_err(|e| format!("could not set shadow permissions: {e}"))?;
        fs::rename(&temporary, path).map_err(|e| format!("could not replace shadow: {e}"))?;
        OpenOptions::new()
            .read(true)
            .open(parent)
            .and_then(|directory| directory.sync_all())
            .map_err(|e| format!("could not sync shadow directory: {e}"))
    })();
    if result.is_err() {
        let _ = fs::remove_file(&temporary);
    }
    result
}

pub fn apply(input: CreateUserInput) -> Result<(), String> {
    let (deploy, target) = validate(&input)?;
    let etc = deploy.join("etc");
    let shadow = etc.join("shadow");
    let home = target
        .join("ostree/deploy/default/var/home")
        .join(&input.username);
    // M16: idempotent create-user. A retry after a crash (or a re-run)
    // must not fail on "user already exists": when the account is already
    // there with matching properties, skip `useradd` and treat it as
    // success. The shadow hash and home-directory steps below are
    // idempotent, so they still run and converge the account.
    if target_user_exists(&etc.join("passwd"), &input.username)? {
        verify_matching_properties(&etc, &input.username)?;
    } else {
        run(
            "/usr/sbin/useradd",
            &[
                "--root",
                deploy.to_str().ok_or("deploy_root is not valid UTF-8")?,
                "-M",
                "-G",
                "wheel,video,audio,render",
                "-s",
                "/bin/bash",
                &input.username,
            ],
        )?;
    }
    replace_shadow_hash(&shadow, &input.username, &input.password_hash)?;
    fs::create_dir_all(&home).map_err(|e| format!("could not create user home: {e}"))?;
    let passwd = fs::read_to_string(etc.join("passwd"))
        .map_err(|e| format!("could not read installed passwd: {e}"))?;
    let (uid, gid) = passwd
        .lines()
        .find_map(|line| {
            let fields: Vec<_> = line.split(':').collect();
            (fields.first() == Some(&input.username.as_str()) && fields.len() > 3)
                .then(|| (fields[2].to_owned(), fields[3].to_owned()))
        })
        .ok_or_else(|| "user not found in passwd after useradd".to_string())?;
    let ownership = format!("{uid}:{gid}");
    run(
        "/usr/bin/chown",
        &[&ownership, home.to_str().ok_or("home is not UTF-8")?],
    )?;
    run(
        "/usr/bin/chmod",
        &["700", home.to_str().ok_or("home is not UTF-8")?],
    )?;
    let skel = etc.join("skel");
    if skel.is_dir() {
        run(
            "/usr/bin/cp",
            &[
                "-rT",
                skel.to_str().ok_or("skel is not UTF-8")?,
                home.to_str().ok_or("home is not UTF-8")?,
            ],
        )?;
        run(
            "/usr/bin/chown",
            &["-R", &ownership, home.to_str().ok_or("home is not UTF-8")?],
        )?;
    }
    let _ = Command::new("/usr/bin/restorecon")
        .args(["-RF", home.to_str().ok_or("home is not UTF-8")?])
        .status();
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn input() -> CreateUserInput {
        CreateUserInput {
            deploy_root: "/target/deploy".into(),
            target_root: "/target".into(),
            username: "kyth_user".into(),
            password_hash: "$6$hash".into(),
        }
    }

    #[test]
    fn validates_bounded_account_request() {
        assert!(validate(&input()).is_ok());
    }

    #[test]
    fn hashes_password_through_stdin_only() {
        let hash = hash_password("native-password").expect("openssl should hash a password");
        assert!(hash.starts_with("$6$"));
        assert!(!hash.contains("native-password"));
    }

    #[test]
    fn rejects_line_breaks_in_password_input() {
        assert!(hash_password("first\nsecond")
            .unwrap_err()
            .contains("line break"));
        assert!(hash_password("first\rsecond")
            .unwrap_err()
            .contains("line break"));
    }

    #[test]
    fn rejects_paths_and_usernames_that_escape_contract() {
        let mut value = input();
        value.deploy_root = "relative".into();
        assert!(validate(&value).is_err());
        let mut value = input();
        value.username = "bad;id".into();
        assert!(validate(&value).is_err());
        for bad in ["Bob", "1abc", "-x", "a.b", "", &"a".repeat(32)] {
            let mut value = input();
            value.username = bad.into();
            assert!(validate(&value).is_err(), "{bad:?}");
        }
        for good in ["alice", "_svc", "a-b_c9", &"a".repeat(31)] {
            let mut value = input();
            value.username = good.into();
            assert!(validate(&value).is_ok(), "{good:?}");
        }
        let mut value = input();
        value.password_hash = "hash\nleak".into();
        assert!(validate(&value).is_err());
    }

    #[test]
    fn shadow_replacement_is_atomic_and_keeps_mode() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("shadow");
        fs::write(&path, "root:!:x\nkyth_user:!:x\n").unwrap();
        fs::set_permissions(&path, fs::Permissions::from_mode(0o640)).unwrap();
        replace_shadow_hash(&path, "kyth_user", "$6$new").unwrap();
        assert_eq!(
            fs::metadata(&path).unwrap().permissions().mode() & 0o777,
            0o640
        );
        // No temp file is left behind, and a failed replacement leaves the
        // original untouched.
        let leftovers: Vec<_> = fs::read_dir(dir.path())
            .unwrap()
            .filter_map(|entry| entry.ok())
            .filter(|entry| entry.file_name() != "shadow")
            .collect();
        assert!(leftovers.is_empty());
        let before = fs::read_to_string(&path).unwrap();
        assert!(replace_shadow_hash(&path, "missing", "$6$x").is_err());
        assert_eq!(fs::read_to_string(&path).unwrap(), before);
    }

    #[test]
    fn replaces_only_selected_shadow_field() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("shadow");
        fs::write(&path, "root:!:x\nkyth_user:!:x\n").unwrap();
        replace_shadow_hash(&path, "kyth_user", "$6$new").unwrap();
        assert_eq!(
            fs::read_to_string(path).unwrap(),
            "root:!:x\nkyth_user:$6$new:x\n"
        );
    }

    fn etc_with_user(dir: &Path, shell: &str, groups: &[(&str, &str)]) {
        let etc = dir.join("etc");
        fs::create_dir_all(&etc).unwrap();
        fs::write(
            etc.join("passwd"),
            format!(
                "root:x:0:0::/root:/bin/bash\nkyth_user:x:1000:1000::/var/home/kyth_user:{shell}\n"
            ),
        )
        .unwrap();
        let mut group = String::from("root:x:0:\n");
        for (name, members) in groups {
            group.push_str(&format!("{name}:x:100:{members}\n"));
        }
        fs::write(etc.join("group"), group).unwrap();
        fs::write(etc.join("shadow"), "root:!:x\nkyth_user:!:x\n").unwrap();
    }

    #[test]
    fn existing_user_with_matching_properties_is_accepted() {
        let dir = tempfile::tempdir().unwrap();
        etc_with_user(
            dir.path(),
            "/bin/bash",
            &[
                ("wheel", "kyth_user"),
                ("video", "kyth_user"),
                ("audio", "kyth_user"),
                ("render", "kyth_user"),
            ],
        );
        assert!(target_user_exists(&dir.path().join("etc/passwd"), "kyth_user").unwrap());
        assert!(!target_user_exists(&dir.path().join("etc/passwd"), "nobody").unwrap());
        verify_matching_properties(&dir.path().join("etc"), "kyth_user")
            .expect("matching properties should be accepted");
    }

    #[test]
    fn existing_user_with_foreign_properties_fails_closed() {
        // Wrong shell.
        let dir = tempfile::tempdir().unwrap();
        etc_with_user(dir.path(), "/bin/zsh", &[("wheel", "kyth_user")]);
        assert!(verify_matching_properties(&dir.path().join("etc"), "kyth_user").is_err());
        // Missing group membership.
        let dir = tempfile::tempdir().unwrap();
        etc_with_user(dir.path(), "/bin/bash", &[("wheel", "kyth_user")]);
        let error = verify_matching_properties(&dir.path().join("etc"), "kyth_user")
            .expect_err("missing group must fail closed");
        assert!(error.contains("video"), "{error}");
    }
}
