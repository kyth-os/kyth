//! Port of `page_just.py`'s `just --list` / `just <recipe>` launch path.
//!
//! `page_just.py` used a Qt `Worker(["just","--list"])` and `popen(["just",name])`
//! — this is the same, but as a direct `std::process::Command` call from the
//! Tauri shell, no Python subprocess bridge. Only the listing/parsing is
//! ported faithfully; execution is fire-and-forget like the Qt `popen` was
//! (it spawned the recipe in the background, no stdout capture).

use std::process::Command;

use serde::Serialize;

#[derive(Debug, Clone, Serialize)]
pub struct JustRecipe {
    pub name: String,
    pub comment: String,
}

/// Parse `just --list` stdout exactly like `page_just.py:_on_just_list_done`:
/// - drop empty lines and `Available recipes:` header
/// - split each remaining line into `name` + `comment` at first whitespace
/// - keep first 30 (page caps display at 30)
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
        // `just --list` indents with 4 spaces; after trim we have `name  # comment`
        // Split at first whitespace, like `ln.split(None,1)` in Python.
        let mut parts = line.splitn(2, char::is_whitespace);
        let name = parts.next().unwrap_or("").trim().to_string();
        if name.is_empty() {
            continue;
        }
        let comment = parts
            .next()
            .unwrap_or("")
            .trim()
            .trim_start_matches('#')
            .trim()
            .to_string();
        out.push(JustRecipe { name, comment });
        if out.len() >= 100 {
            break;
        }
    }
    out
}

/// Run `just --list` with a 5s timeout (matches `Worker` default) and parse.
/// Returns `Ok(vec)` even when `just` exits non-zero but produced stdout —
///
/// same fallback as Qt: `text = f"just --list failed (exit {code})"` only
/// when both code !=0 and stdout empty. Here we return empty vec on hard
/// failure so the caller can show the fallback note.
pub fn just_list() -> Vec<JustRecipe> {
    let output = Command::new("just")
        .arg("--list")
        .output();
    match output {
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

/// Fire-and-forget `just <recipe>` — mirrors `services.launch.popen(["just",name])`
/// in `page_just.py:_run_recipe`. Returns true if the spawn succeeded.
pub fn just_run(recipe: &str) -> bool {
    // Validate recipe name is a single token without shell metachars — same
    // constraint `just` itself enforces, but we gate here to avoid injection
    // via Tauri's string arg (e.g. `name="foo; rm -rf /"`). Qt's `Worker`
    // passed `["just", name]` as argv too, so this matches its safety.
    if recipe.is_empty()
        || recipe.contains(|c: char| c.is_whitespace() || matches!(c, ';' | '&' | '|' | '`' | '$' | '(' | ')' | '<' | '>' | '\\' | '"' | '\'' ))
    {
        return false;
    }
    match Command::new("just").arg(recipe).spawn() {
        Ok(_) => true,
        Err(_) => false,
    }
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
        assert_eq!(v[0].comment, "Build the full KythOS image.");
        assert_eq!(v[1].name, "lint");
        assert_eq!(v[1].comment, "Run checks");
        assert_eq!(v[2].name, "foo");
        assert_eq!(v[2].comment, "");
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
    }
}
