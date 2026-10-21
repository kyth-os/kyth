//! Bounded offline installer-account creation.
//!
//! The password hash is accepted only in the operation body (stdin) and is
//! never placed in argv, logs, or a diagnostic response.

use std::fs::{self, OpenOptions};
use std::io::Write;
use std::os::fd::AsRawFd;
use std::os::unix::fs::{MetadataExt, OpenOptionsExt, PermissionsExt};
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

/// No Debug impl on purpose: the password hash must never be formattable
/// into a log line, event, or diagnostic message.
#[derive(Clone, serde::Deserialize, serde::Serialize)]
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

/// Offline useradd requires supplementary groups in /etc/group even when NSS
/// can see the immutable /usr/lib/group database. Preserve the image's GIDs and
/// members rather than inventing IDs or running all sysusers offline.
fn expected_group_overlay(local: &str, base: &str) -> Result<String, String> {
    fn records(text: &str) -> Result<std::collections::BTreeMap<&str, (u32, &str)>, String> {
        let mut result = std::collections::BTreeMap::new();
        for line in text
            .lines()
            .filter(|line| !line.is_empty() && !line.starts_with('#'))
        {
            let fields: Vec<_> = line.split(':').collect();
            if fields.len() != 4 || fields[0].is_empty() {
                return Err("installed group database has a malformed record".into());
            }
            let gid = fields[2]
                .parse::<u32>()
                .map_err(|_| "installed group database has an invalid GID".to_string())?;
            if let Some(previous) = result.insert(fields[0], (gid, line)) {
                if previous != (gid, line) {
                    return Err("installed group database has conflicting duplicate records".into());
                }
            }
        }
        Ok(result)
    }
    let local_records = records(local)?;
    let base_records = records(base)?;
    let mut output = local.to_string();
    for group in EXPECTED_GROUPS {
        if local_records.contains_key(group) {
            continue;
        }
        let (gid, record) = base_records.get(group).ok_or_else(|| {
            format!("required group {group} is absent from installed group databases")
        })?;
        if local_records
            .iter()
            .any(|(name, (existing_gid, _))| *name != *group && existing_gid == gid)
        {
            return Err(format!(
                "required group {group} conflicts with an installed GID"
            ));
        }
        if !output.is_empty() && !output.ends_with('\n') {
            output.push('\n');
        }
        output.push_str(record);
        output.push('\n');
    }
    Ok(output)
}

fn ensure_expected_groups(deploy: &Path) -> Result<(), String> {
    let path = deploy.join("etc/group");
    let local = fs::read_to_string(&path)
        .map_err(|error| format!("could not read installed group database: {error}"))?;
    let base = match fs::read_to_string(deploy.join("usr/lib/group")) {
        Ok(base) => base,
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => String::new(),
        Err(error) => return Err(format!("could not read immutable group database: {error}")),
    };
    let overlay = expected_group_overlay(&local, &base)?;
    if overlay != local {
        write_replacing(&path, overlay.as_bytes())?;
    }
    Ok(())
}

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
fn copy_account_xattrs(source: &fs::File, target: &fs::File) -> Result<(), String> {
    // Linux bounds both xattr lists and values at 64 KiB. Keep the helper's
    // allocations bounded too; failures must not publish an unlabeled shadow.
    let size = unsafe { libc::flistxattr(source.as_raw_fd(), std::ptr::null_mut(), 0) };
    if size < 0 {
        let error = std::io::Error::last_os_error();
        return if error.raw_os_error() == Some(libc::ENOTSUP) {
            Ok(())
        } else {
            Err(format!("could not inspect account labels: {error}"))
        };
    }
    if size > 65536 {
        return Err("account metadata list is too large".into());
    }
    let mut names = vec![0u8; size as usize];
    let size =
        unsafe { libc::flistxattr(source.as_raw_fd(), names.as_mut_ptr().cast(), names.len()) };
    if size < 0 || size as usize > names.len() {
        return Err("could not read a bounded account label list".into());
    }
    for bytes in names[..size as usize]
        .split(|byte| *byte == 0)
        .filter(|name| !name.is_empty())
    {
        // Content signatures and executable capabilities cannot be carried
        // across a credential-file content change. Preserve SELinux/ACL/user
        // metadata, not signatures over the old bytes.
        if bytes == b"security.ima" || bytes == b"security.evm" || bytes == b"security.capability" {
            continue;
        }
        let name = std::ffi::CString::new(bytes).map_err(|_| "invalid account label name")?;
        let length =
            unsafe { libc::fgetxattr(source.as_raw_fd(), name.as_ptr(), std::ptr::null_mut(), 0) };
        if !(0..=65536).contains(&length) {
            return Err("could not inspect account label value".into());
        }
        let mut value = vec![0u8; length as usize];
        let read = unsafe {
            libc::fgetxattr(
                source.as_raw_fd(),
                name.as_ptr(),
                value.as_mut_ptr().cast(),
                value.len(),
            )
        };
        if read != length {
            return Err("could not read stable account label value".into());
        }
        if unsafe {
            libc::fsetxattr(
                target.as_raw_fd(),
                name.as_ptr(),
                value.as_ptr().cast(),
                value.len(),
                0,
            )
        } != 0
        {
            return Err(format!(
                "could not preserve account label: {}",
                std::io::Error::last_os_error()
            ));
        }
    }
    Ok(())
}

fn write_replacing(path: &Path, contents: &[u8]) -> Result<(), String> {
    let source = OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_NOFOLLOW | libc::O_CLOEXEC)
        .open(path)
        .map_err(|error| format!("could not open installed account database: {error}"))?;
    let metadata = source.metadata().map_err(|error| error.to_string())?;
    let mode = metadata.permissions().mode() & 0o7777;
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
        if unsafe { libc::fchown(file.as_raw_fd(), metadata.uid(), metadata.gid()) } != 0 {
            return Err(format!(
                "could not preserve account ownership: {}",
                std::io::Error::last_os_error()
            ));
        }
        fs::set_permissions(&temporary, fs::Permissions::from_mode(mode))
            .map_err(|e| format!("could not set shadow permissions: {e}"))?;
        copy_account_xattrs(&source, &file)?;
        file.sync_all()
            .map_err(|e| format!("could not sync account metadata: {e}"))?;
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

/// Hand off to the real login manager only after every account operation
/// succeeded. Plasma Setup tests this flag, not the presence of human users.
fn complete_plasma_setup(etc: &Path) -> Result<(), String> {
    let mut stale = Vec::new();
    for backend in ["plasmalogin.conf.d", "sddm.conf.d"] {
        let parent = etc.join(backend);
        match fs::symlink_metadata(&parent) {
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => continue,
            Ok(metadata) if metadata.is_dir() && !metadata.file_type().is_symlink() => {}
            _ => return Err("Plasma Setup configuration parent is not a real directory".into()),
        }
        let path = parent.join("99-plasma-setup.conf");
        match fs::symlink_metadata(&path) {
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => continue,
            Ok(metadata) if metadata.is_file() && !metadata.file_type().is_symlink() => {}
            _ => return Err("Plasma Setup autologin configuration is not a regular file".into()),
        }
        let contents = fs::read_to_string(&path)
            .map_err(|error| format!("could not read Plasma Setup autologin: {error}"))?;
        if !contents.lines().any(|line| {
            line.split_once('=')
                .is_some_and(|(key, value)| key.trim() == "User" && value.trim() == "plasma-setup")
        }) {
            return Err("refusing to remove an unmanaged Plasma Setup autologin file".into());
        }
        stale.push(path);
    }
    for path in stale {
        fs::remove_file(&path)
            .map_err(|error| format!("could not remove Plasma Setup autologin: {error}"))?;
        fs::File::open(path.parent().ok_or("setup configuration has no parent")?)
            .and_then(|directory| directory.sync_all())
            .map_err(|error| format!("could not sync Plasma Setup autologin directory: {error}"))?;
    }
    let marker = etc.join("plasma-setup-done");
    let file = OpenOptions::new()
        .write(true)
        .create(true)
        .truncate(false)
        .mode(0o644)
        .custom_flags(libc::O_NOFOLLOW | libc::O_NONBLOCK)
        .open(&marker)
        .map_err(|error| format!("could not complete Plasma Setup: {error}"))?;
    if !file
        .metadata()
        .map_err(|error| error.to_string())?
        .is_file()
    {
        return Err("Plasma Setup completion marker is not a regular file".into());
    }
    file.sync_all()
        .map_err(|error| format!("could not sync Plasma Setup marker: {error}"))?;
    fs::File::open(etc)
        .and_then(|directory| directory.sync_all())
        .map_err(|error| format!("could not sync Plasma Setup completion: {error}"))
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
        ensure_expected_groups(&deploy)?;
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
    complete_plasma_setup(&etc)
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
    fn failed_account_provisioning_does_not_complete_plasma_setup() {
        let temp = tempfile::tempdir().unwrap();
        let etc = temp.path().join("etc");
        fs::create_dir(&etc).unwrap();
        fs::write(
            etc.join("passwd"),
            "kyth_user:x:1000:1000::/home/kyth_user:/bin/bash\n",
        )
        .unwrap();
        fs::write(etc.join("group"), "").unwrap();
        let request = CreateUserInput {
            deploy_root: temp.path().to_string_lossy().into_owned(),
            target_root: temp.path().to_string_lossy().into_owned(),
            username: "kyth_user".into(),
            password_hash: "$6$synthetic-fixture".into(),
        };
        assert!(apply(request).unwrap_err().contains("wheel"));
        assert!(!etc.join("plasma-setup-done").exists());
    }

    #[test]
    fn plasma_setup_handoff_rejects_symlinked_autologin_without_touching_target() {
        let temp = tempfile::tempdir().unwrap();
        let etc = temp.path().join("etc");
        fs::create_dir_all(etc.join("plasmalogin.conf.d")).unwrap();
        let outside = temp.path().join("unrelated.conf");
        fs::write(&outside, "keep this file").unwrap();
        std::os::unix::fs::symlink(
            &outside,
            etc.join("plasmalogin.conf.d/99-plasma-setup.conf"),
        )
        .unwrap();
        assert!(complete_plasma_setup(&etc).is_err());
        assert!(!etc.join("plasma-setup-done").exists());
        assert_eq!(fs::read_to_string(outside).unwrap(), "keep this file");
    }

    #[test]
    fn atomic_account_replacement_preserves_owner_mode_and_extended_labels() {
        use std::os::unix::ffi::OsStrExt;
        use std::os::unix::fs::MetadataExt;
        let temp = tempfile::tempdir().unwrap();
        let path = temp.path().join("shadow");
        fs::write(&path, "synthetic-original\n").unwrap();
        fs::set_permissions(&path, fs::Permissions::from_mode(0o600)).unwrap();
        let name = std::ffi::CString::new("user.kyth-account-metadata").unwrap();
        let cpath = std::ffi::CString::new(path.as_os_str().as_bytes()).unwrap();
        let label = b"original-label";
        assert_eq!(
            unsafe {
                libc::setxattr(
                    cpath.as_ptr(),
                    name.as_ptr(),
                    label.as_ptr().cast(),
                    label.len(),
                    0,
                )
            },
            0
        );
        let before = fs::metadata(&path).unwrap();
        write_replacing(&path, b"synthetic-replacement\n").unwrap();
        let after = fs::metadata(&path).unwrap();
        let mut value = [0u8; 64];
        let length = unsafe {
            libc::getxattr(
                cpath.as_ptr(),
                name.as_ptr(),
                value.as_mut_ptr().cast(),
                value.len(),
            )
        };
        assert_eq!(
            length,
            label.len() as isize,
            "account replacement discarded extended metadata"
        );
        assert_eq!(&value[..length as usize], label);
        assert_eq!(
            (before.uid(), before.gid(), before.mode()),
            (after.uid(), after.gid(), after.mode())
        );
    }

    #[test]
    fn successful_account_retry_completes_plasma_setup_and_clears_setup_autologin() {
        let temp = tempfile::tempdir().unwrap();
        let deploy = temp.path().join("deployment");
        let etc = deploy.join("etc");
        fs::create_dir_all(&etc).unwrap();
        let uid = unsafe { libc::geteuid() }.max(1000);
        let gid = unsafe { libc::getegid() }.max(1000);
        fs::write(
            etc.join("passwd"),
            format!("kyth_user:x:{uid}:{gid}::/home/kyth_user:/bin/bash\n"),
        )
        .unwrap();
        fs::write(etc.join("shadow"), "kyth_user:!:20000:0:99999:7:::\n").unwrap();
        fs::write(etc.join("group"), "wheel:x:10:kyth_user\nvideo:x:39:kyth_user\naudio:x:63:kyth_user\nrender:x:105:kyth_user\n").unwrap();
        for backend in ["plasmalogin.conf.d", "sddm.conf.d"] {
            fs::create_dir(etc.join(backend)).unwrap();
            fs::write(
                etc.join(backend).join("99-plasma-setup.conf"),
                "[Autologin]\nUser=plasma-setup\nSession=plasma\n",
            )
            .unwrap();
        }
        let request = CreateUserInput {
            deploy_root: deploy.to_string_lossy().into_owned(),
            target_root: temp.path().to_string_lossy().into_owned(),
            username: "kyth_user".into(),
            password_hash: "$6$synthetic-fixture".into(),
        };
        apply(request.clone()).unwrap();
        assert!(
            etc.join("plasma-setup-done").is_file(),
            "a successfully provisioned login must bypass Plasma Setup"
        );
        for backend in ["plasmalogin.conf.d", "sddm.conf.d"] {
            assert!(!etc.join(backend).join("99-plasma-setup.conf").exists());
        }
        apply(request).unwrap();
    }

    #[test]
    fn offline_account_materializes_immutable_groups_with_their_original_ids() {
        let local = "root:x:0:\nwheel:x:10:\n";
        let base =
            "wheel:x:10:\nvideo:x:39:camera\naudio:x:63:\nrender:x:105:\nvideo:x:39:camera\n";
        let result = expected_group_overlay(local, base).unwrap();
        assert_eq!(
            result,
            format!("{local}video:x:39:camera\naudio:x:63:\nrender:x:105:\n")
        );
        assert_eq!(expected_group_overlay(&result, base).unwrap(), result);
    }

    #[test]
    fn offline_group_overlay_rejects_missing_groups_and_gid_conflicts() {
        let base = "wheel:x:10:\nvideo:x:39:\naudio:x:63:\nrender:x:105:\n";
        assert!(expected_group_overlay("wheel:x:10:\nforeign:x:39:\n", base).is_err());
        assert!(expected_group_overlay("wheel:x:10:\n", "").is_err());
        assert!(expected_group_overlay("wheel:x:10:\n", &format!("{base}video:x:40:\n")).is_err());
    }

    #[test]
    fn materializing_expected_groups_is_atomic_and_preserves_existing_members() {
        let temp = tempfile::tempdir().unwrap();
        fs::create_dir_all(temp.path().join("etc")).unwrap();
        fs::create_dir_all(temp.path().join("usr/lib")).unwrap();
        let path = temp.path().join("etc/group");
        fs::write(&path, "root:x:0:\nwheel:x:10:existing\n").unwrap();
        fs::set_permissions(&path, fs::Permissions::from_mode(0o644)).unwrap();
        fs::write(
            temp.path().join("usr/lib/group"),
            "wheel:x:10:\nvideo:x:39:\naudio:x:63:\nrender:x:105:\n",
        )
        .unwrap();
        ensure_expected_groups(temp.path()).unwrap();
        let result = fs::read_to_string(&path).unwrap();
        assert!(result.contains("wheel:x:10:existing\n"));
        assert!(result.contains("video:x:39:\n"));
        assert_eq!(
            fs::metadata(&path).unwrap().permissions().mode() & 0o777,
            0o644
        );
        ensure_expected_groups(temp.path()).unwrap();
        assert_eq!(fs::read_to_string(&path).unwrap(), result);
        assert!(!path.with_extension("kyth-tmp").exists());
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
