//! Port of `page_just.py`'s `just --list` / `just <recipe>` launch path.
//!
//! `page_just.py` used a Qt `Worker(["just","--list"])` and `popen(["just",name])`
//! — this is the same, but as a direct `std::process::Command` call from the
//! Tauri shell, no Python subprocess bridge. Only the listing/parsing is
//! ported faithfully; execution is fire-and-forget like the Qt `popen` was
//! (it spawned the recipe in the background, no stdout capture).
//!
//! Two things the Qt version got wrong and this one does not:
//!
//! 1. Bare `just` resolves a justfile by walking up from the process working
//!    directory. The Hub's working directory is whatever the `.desktop`
//!    launcher gives it — `/` or `$HOME` — and neither has a justfile, so
//!    `just --list` returned "error: no justfile found" and every recipe
//!    launch was a no-op. Kyth's recipes live in ublue's justfile, which is
//!    exactly what `ujust` exists to point `just` at:
//!    `JUST_JUSTFILE=/usr/share/ublue-os/justfile /usr/bin/just "$@"`.
//!    Setting that variable also makes `just` treat the justfile's parent as
//!    the working directory, so this matches `ujust` exactly (verified
//!    against just 1.58, the version the image ships).
//! 2. Recipes use `sudo`, never `pkexec` (see `build_files/just/kyth/*.just`),
//!    so a recipe spawned without a terminal has nowhere to prompt and fails
//!    silently — and a report recipe like `update-health` has nowhere to
//!    print. Launches therefore go through a terminal emulator when one is
//!    installed, which is also what makes the Hub's "running in its own
//!    window" wording true.

use std::path::Path;
use std::process::Command;

use serde::Serialize;

/// The justfile `ujust` points `just` at — see the module docs. Kyth's
/// recipes are imported into it by `branding/31-ujust-recipes.sh`.
const UBLUE_JUSTFILE: &str = "/usr/share/ublue-os/justfile";

/// Terminals tried, in order, for a recipe launch. Both take the command to
/// run after `-e` and pass the remaining arguments to it untouched. Kinoite
/// ships konsole (it is in the Kickoff favourites this image sets); xterm is
/// only a fallback for a stripped session.
const TERMINALS: &[&str] = &["/usr/bin/konsole", "/usr/bin/xterm"];

/// Wrapper run inside the terminal so the window stays up after the recipe
/// finishes — otherwise an audit or health report scrolls past and closes.
/// The recipe is passed as an argument, never interpolated into this text.
const KEEP_OPEN: &str = r#"just "$@"; status=$?; printf '\n[exit %s — press Enter to close]' "$status"; read -r _"#;

#[derive(Debug, Clone, Serialize)]
pub struct JustRecipe {
    pub name: String,
    /// Parameters as `just --list` prints them (`flavor="fedora"`), empty for
    /// a recipe that takes none. `just_run` spawns the name with no arguments,
    /// so a non-empty `params` means running it from the Hub would silently
    /// use the defaults — the listing renders those rows as text, not buttons.
    pub params: String,
    pub comment: String,
}

/// What a launch actually did, so the caller can say so instead of guessing.
/// `in_terminal` false means the recipe was spawned with no tty: it cannot
/// prompt for a password and its output goes nowhere.
#[derive(Debug, Clone, Copy, Serialize)]
pub struct JustLaunch {
    pub launched: bool,
    pub in_terminal: bool,
}
/// Parse `just --list` stdout exactly like `page_just.py:_on_just_list_done`:
/// - drop empty lines and `Available recipes:` header
/// - split each remaining line into `name` + `comment` at first whitespace
/// - keep first 500 (the shipped justfile has ~200 recipes; the React
/// listing filters over the whole set and caps its own display at 30,
/// so cutting the backend list short just hides recipes from the filter)
fn parse_just_list(stdout: &str) -> Vec<JustRecipe> {
    let mut out = Vec::new();
    for raw in stdout.lines() {
        let line = raw.trim();
        if line.is_empty() {
            continue;
        }
        if line.starts_with("Available recipes:") {
            continue;
        }
        // Every kyth recipe carries `[group('KythOS')]`, so real `just --list`
        // output puts a `[KythOS]` heading line above them. It parses as a
        // name with no parameters, which used to give it a button that spawns
        // `just [KythOS]` and fails. Headings are never runnable.
        if line.starts_with('[') && line.ends_with(']') {
            continue;
        }
        // `just --list` indents with 4 spaces; after trim we have
        // `name [params]  # comment`. Split at first whitespace for the name
        // (like `ln.split(None,1)` in Python), then at the first `#` to keep
        // parameters out of the comment — page_just.py folded them together,
        // but the React listing needs them apart to decide button vs text.
        let mut parts = line.splitn(2, char::is_whitespace);
        let name = parts.next().unwrap_or("").trim().to_string();
        if name.is_empty() {
            continue;
        }
        let rest = parts.next().unwrap_or("").trim();
        let (params, comment) = match rest.split_once('#') {
            Some((before, after)) => (before.trim().to_string(), after.trim().to_string()),
            None => (rest.to_string(), String::new()),
        };
        out.push(JustRecipe { name, params, comment });
        if out.len() >= 500 {
            break;
        }
    }
    out
}

/// Point `just` at ublue's justfile, exactly as the `ujust` wrapper does.
/// Split out from `configure` so a test can pin the behaviour against a
/// temporary path instead of the real `/usr` one, which is absent off-image.
fn justfile_env_for(justfile: &Path) -> Option<String> {
    justfile.is_file().then(|| justfile.to_string_lossy().into_owned())
}

fn configure(cmd: &mut Command) {
    if let Some(justfile) = justfile_env_for(Path::new(UBLUE_JUSTFILE)) {
        cmd.env("JUST_JUSTFILE", justfile);
    }
}

fn find_terminal() -> Option<&'static str> {
    TERMINALS.iter().copied().find(|term| Path::new(term).exists())
}

/// A recipe name (or a fixed argument) is safe to hand to `just` when it is
/// a single bare token. Allowlist rather than a metacharacter blocklist: a
/// just recipe name is alphanumerics, `-` and `_` (Guardian also passes
/// dotted ids like `audio.restart`, which simply do not resolve). The
/// blocklist this replaces let `[KythOS]` through, because brackets are not
/// shell metacharacters — harmless to spawn, but it meant nothing upstream
/// had to be careful about what it handed us.
fn is_bare_token(token: &str) -> bool {
    !token.is_empty()
        && token.chars().all(|c| c.is_ascii_alphanumeric() || matches!(c, '-' | '_' | '.'))
}

/// Build the argv for a launch. Pure, so a test can pin the invocation —
/// the bug this module used to have was entirely in how `just` was invoked,
/// which the parsing tests could not see.
///
/// With a terminal, the recipe is passed as an argument to `KEEP_OPEN`
/// rather than spliced into it, so nothing about the name reaches a shell
/// as text.
fn launch_argv(terminal: Option<&str>, recipe: &str, args: &[&str]) -> Vec<String> {
    let mut argv: Vec<String> = Vec::new();
    if let Some(term) = terminal {
        argv.push(term.to_string());
        argv.push("-e".to_string());
        argv.push("/bin/bash".to_string());
        argv.push("-c".to_string());
        argv.push(KEEP_OPEN.to_string());
        // $0 inside KEEP_OPEN; the recipe and its arguments become "$@".
        argv.push("kyth-hub".to_string());
    } else {
        argv.push("just".to_string());
    }
    argv.push(recipe.to_string());
    argv.extend(args.iter().map(|arg| (*arg).to_string()));
    argv
}

/// Run `just --list` with the justfile `ujust` uses and parse.
/// Returns `Ok(vec)` even when `just` exits non-zero but produced stdout —
///
/// same fallback as Qt: `text = f"just --list failed (exit {code})"` only
/// when both code !=0 and stdout empty. Here we return empty vec on hard
/// failure so the caller can show the fallback note.
pub fn just_list() -> Vec<JustRecipe> {
    let mut cmd = Command::new("just");
    cmd.arg("--list");
    configure(&mut cmd);
    match cmd.output() {
        Ok(out) => {
            let stdout = String::from_utf8_lossy(&out.stdout).to_string();
            let parsed = parse_just_list(&stdout);
            if !parsed.is_empty() {
                return parsed;
            }
            // If stdout empty and exit !=0, treat as no recipes (caller shows fallback)
            // — don't surface stderr as recipes.
            Vec::new()
        }
        Err(_) => Vec::new(),
    }
}

/// Fire-and-forget launch of `just <recipe> <args…>` in a terminal window.
/// `args` is for callers that pass a fixed, non-user-controlled argument
/// (`switch-channel stable`); every element is validated like the recipe
/// name, so a caller cannot smuggle a flag or a second recipe through it.
pub fn just_launch(recipe: &str, args: &[&str]) -> JustLaunch {
    if !is_bare_token(recipe) || !args.iter().all(|arg| is_bare_token(arg)) {
        return JustLaunch { launched: false, in_terminal: false };
    }
    let terminal = find_terminal();
    let argv = launch_argv(terminal, recipe, args);
    let mut cmd = Command::new(&argv[0]);
    cmd.args(&argv[1..]);
    configure(&mut cmd);
    JustLaunch { launched: cmd.spawn().is_ok(), in_terminal: terminal.is_some() }
}

/// Fire-and-forget `just <recipe>` — mirrors `services.launch.popen(["just",name])`
/// in `page_just.py:_run_recipe`. Returns true if the spawn succeeded.
pub fn just_run(recipe: &str) -> bool {
    just_launch(recipe, &[]).launched
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parse_basic() {
        let out = "Available recipes:\n    build    # Build the full KythOS image.\n    lint     # Run checks\n    foo\n";
        let v = parse_just_list(out);
        assert_eq!(v.len(), 3);
        assert_eq!(v[0].name, "build");
        assert_eq!(v[0].params, "");
        assert_eq!(v[0].comment, "Build the full KythOS image.");
        assert_eq!(v[1].name, "lint");
        assert_eq!(v[1].comment, "Run checks");
        assert_eq!(v[2].name, "foo");
        assert_eq!(v[2].params, "");
        assert_eq!(v[2].comment, "");
    }

    #[test]
    fn parse_keeps_parameters_out_of_the_comment() {
        // `just switch-kernel` with no argument means `fedora`. The listing
        // has to surface that, or a row in the Hub becomes a one-click switch
        // off the CachyOS default under a label that only says the name.
        let out = "Available recipes:\n    switch-kernel flavor=\"fedora\"   # Switch the installed kernel.\n    gaming-mode  # Gaming profile\n";
        let v = parse_just_list(out);
        assert_eq!(v[0].name, "switch-kernel");
        assert_eq!(v[0].params, "flavor=\"fedora\"");
        assert_eq!(v[0].comment, "Switch the installed kernel.");
        assert_eq!(v[1].params, "");
        assert_eq!(v[1].comment, "Gaming profile");
    }

    #[test]
    fn parse_keeps_more_recipes_than_the_justfile_has() {
        // The shipped justfile lists ~200 recipes and the section filters
        // over the whole list, so a cap below that silently hides the tail.
        let mut out = String::from("Available recipes:\n");
        for i in 0..300 {
            out.push_str(&format!("    recipe-{i}  # comment\n"));
        }
        assert_eq!(parse_just_list(&out).len(), 300);
    }

    #[test]
    fn parse_empty() {
        assert!(parse_just_list("").is_empty());
        assert!(parse_just_list("Available recipes:\n").is_empty());
    }

    #[test]
    fn just_run_rejects_injection() {
        assert!(!just_run("foo; rm -rf /"));
        assert!(!just_run("foo && bar"));
        assert!(!just_run(""));
        assert!(!just_run("foo bar"));
        assert!(!just_run("[KythOS]"));
    }

    #[test]
    fn launch_rejects_arguments_that_are_not_bare_tokens() {
        // `args` is for fixed literals like `switch-channel stable`; a flag
        // or a second word would change what the recipe does.
        assert!(!just_launch("switch-channel", &["--dry-run"]).launched);
        assert!(!just_launch("switch-channel", &["stable; reboot"]).launched);
    }

    /// The justfile ublue's `ujust` wrapper exports:
    /// `JUST_JUSTFILE="/usr/share/ublue-os/justfile" /usr/bin/just "${@}"`.
    /// `branding/31-ujust-recipes.sh` appends kyth's import to that file, so
    /// this is where the recipes are. Without it, `just` walks up from the
    /// Hub's working directory, finds nothing, and every launch is a no-op.
    #[test]
    fn justfile_is_the_one_ujust_uses() {
        assert_eq!(UBLUE_JUSTFILE, "/usr/share/ublue-os/justfile");
    }

    #[test]
    fn justfile_env_is_set_only_when_the_justfile_is_installed() {
        let dir = std::env::temp_dir().join("kyth-just-env-test");
        let _ = std::fs::create_dir_all(&dir);
        let justfile = dir.join("justfile");
        std::fs::write(&justfile, "default:\n    @true\n").expect("write justfile");
        assert_eq!(justfile_env_for(&justfile).as_deref(), Some(justfile.to_string_lossy().as_ref()));
        assert_eq!(justfile_env_for(&dir.join("absent")), None);
        let _ = std::fs::remove_file(&justfile);
    }

    #[test]
    fn launch_argv_runs_the_recipe_through_a_terminal_when_one_exists() {
        let argv = launch_argv(Some("/usr/bin/konsole"), "update-health", &[]);
        assert_eq!(argv[0], "/usr/bin/konsole");
        assert_eq!(argv[1], "-e");
        assert_eq!(argv[2], "/bin/bash");
        assert_eq!(argv[3], "-c");
        assert!(argv[4].contains(r#"just "$@""#), "{}", argv[4]);
        // The recipe is an argument to the wrapper, never part of its text.
        assert!(!argv[4].contains("update-health"));
        assert_eq!(argv[6], "update-health");
    }

    #[test]
    fn launch_argv_falls_back_to_a_bare_spawn_without_a_terminal() {
        assert_eq!(
            launch_argv(None, "switch-channel", &["stable"]),
            vec!["just", "switch-channel", "stable"],
        );
    }

    /// Captured from `just --justfile build_files/just/kyth.just --list`
    /// (just 1.58) — the heading is what `[group('KythOS')]` produces, and
    /// the two parameter forms are the ones the shipped recipes use.
    #[test]
    fn parse_real_list_output() {
        let out = concat!(
            "Available recipes:\n",
            "    [KythOS]\n",
            "    ai-dev-enter\n",
            "    gaming-audit mode=\"\"                   # Perf audit\n",
            "    retry-quarantined-update digest        # Usage: ujust retry-quarantined-update sha256:...\n",
            "    switch-kernel flavor=\"fedora\"          # ujust switch-kernel cachy\n",
        );
        let v = parse_just_list(out);
        let names: Vec<&str> = v.iter().map(|r| r.name.as_str()).collect();
        assert_eq!(names, ["ai-dev-enter", "gaming-audit", "retry-quarantined-update", "switch-kernel"]);
        assert_eq!(v[0].params, "");
        assert_eq!(v[1].params, "mode=\"\"");
        assert_eq!(v[2].params, "digest");
        assert_eq!(v[3].params, "flavor=\"fedora\"");
        assert_eq!(v[3].comment, "ujust switch-kernel cachy");
    }
}
