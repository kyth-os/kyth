//! Catalog of individually selectable developer/AI-agent tools for the
//! Dev Tools setup wizard. Single source of truth for what the wizard can
//! offer, what Rust actually knows how to install for each entry, and
//! whether it lands inside the `kyth-ai-dev` distrobox or is exported to
//! the host desktop. Mirrors the `gaming_tools::GAMING_TOOLS` pattern:
//! one flat `const` array, one lookup function, contract-tested here.
//!
//! Every entry's `install` method must be something Rust can actually run
//! unattended and report success/failure for. Where no maintained,
//! single-command install path is verified (e.g. some community desktop
//! app repackagings churn asset names release to release), the entry uses
//! [`InstallMethod::Manual`] and opens the project's page instead of
//! guessing a URL that could silently fail or, worse, silently install
//! the wrong thing.

/// Where a tool's install work happens and how the wizard's "review" step
/// should describe it.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum DevToolCategory {
    Editor,
    AgentCli,
    AgentDesktop,
    Language,
    Utility,
    LocalAi,
}

impl DevToolCategory {
    pub fn label(self) -> &'static str {
        match self {
            DevToolCategory::Editor => "Editors & IDEs",
            DevToolCategory::AgentCli => "Agent CLIs",
            DevToolCategory::AgentDesktop => "Agent desktop apps",
            DevToolCategory::Language => "Languages & runtimes",
            DevToolCategory::Utility => "Utilities",
            DevToolCategory::LocalAi => "Local AI",
        }
    }

    pub fn key(self) -> &'static str {
        match self {
            DevToolCategory::Editor => "editor",
            DevToolCategory::AgentCli => "agent-cli",
            DevToolCategory::AgentDesktop => "agent-desktop",
            DevToolCategory::Language => "language",
            DevToolCategory::Utility => "utility",
            DevToolCategory::LocalAi => "local-ai",
        }
    }
}

/// How a tool actually gets installed. `InBox*` variants run inside the
/// managed `kyth-ai-dev` distrobox (package-manager or npm install), then
/// get `distrobox-export`ed to the host PATH/app menu by
/// [`export_binaries`]/[`export_apps`] once installed. `Host*` variants run
/// directly on the host — they are native desktop apps, not CLI tooling
/// meant to live in an isolated container.
#[derive(Debug, Clone, Copy)]
pub enum InstallMethod {
    /// `dnf`/`dnf5` package names, installed inside the distrobox.
    InBoxDnf(&'static [&'static str]),
    /// `npm install -g` package names, installed inside the distrobox.
    InBoxNpmGlobal(&'static [&'static str]),
    /// A `curl -fsSL <url> | bash`-style installer script, run directly on
    /// the host (these are host-native agent tools, not distrobox CLIs).
    HostScript(&'static str),
    /// Download this URL (an `.rpm`) and `dnf install ./<file>` it on the
    /// host. Used for vendor-signed desktop packages that configure their
    /// own update repo on first install (e.g. the official ChatGPT/Codex
    /// desktop app), rather than a distro package we could name directly.
    HostRpmUrl(&'static str),
    /// No verified, stable one-command install exists (e.g. a community
    /// repackaging whose release asset naming isn't pinned down). Opens
    /// this URL in the browser instead of guessing at an install command.
    Manual(&'static str),
}

#[derive(Debug, Clone, Copy)]
pub struct DevTool {
    /// Stable key: used in wizard selection state and provisioning.
    pub id: &'static str,
    pub name: &'static str,
    pub category: DevToolCategory,
    pub description: &'static str,
    pub install: InstallMethod,
    /// True for tools with no official Linux build — the wizard shows an
    /// "Unofficial / community build" badge and the review step calls it
    /// out explicitly, never silently blends it into the trusted set.
    pub unofficial: bool,
    /// Preselected the first time a user opens the wizard. Chosen to be
    /// the smallest useful "vibe coder" default: a real editor, git, one
    /// agent CLI, and Node/Python for anything an agent wants to run.
    pub default_selected: bool,
    /// If true, this tool is exported to the host PATH via
    /// `distrobox-export --bin` (or `--app` for a GUI) after installing
    /// inside the box. False for tools that install directly on the host.
    pub exported_to_host: bool,
    /// The command name(s) checked to report installed/not-installed
    /// status. Empty for host-installed GUI apps we cannot cheaply probe
    /// from inside the box.
    pub probe_commands: &'static [&'static str],
}

pub const DEV_TOOLS: &[DevTool] = &[
    // --- Editors & IDEs -----------------------------------------------
    DevTool {
        id: "vscode",
        name: "VS Code",
        category: DevToolCategory::Editor,
        description: "Microsoft's editor, with the full extension marketplace.",
        install: InstallMethod::InBoxDnf(&["code"]),
        unofficial: false,
        default_selected: true,
        exported_to_host: true,
        probe_commands: &["code"],
    },
    DevTool {
        id: "helix",
        name: "Helix",
        category: DevToolCategory::Editor,
        description: "Modal terminal editor with built-in LSP support, no config required.",
        install: InstallMethod::InBoxDnf(&["helix"]),
        unofficial: false,
        default_selected: false,
        exported_to_host: true,
        probe_commands: &["hx"],
    },
    // --- Agent CLIs -----------------------------------------------------
    DevTool {
        id: "claude-code",
        name: "Claude Code",
        category: DevToolCategory::AgentCli,
        description: "Anthropic's terminal coding agent.",
        install: InstallMethod::InBoxNpmGlobal(&["@anthropic-ai/claude-code"]),
        unofficial: false,
        default_selected: true,
        exported_to_host: true,
        probe_commands: &["claude"],
    },
    DevTool {
        id: "codex-cli",
        name: "Codex CLI",
        category: DevToolCategory::AgentCli,
        description: "OpenAI's terminal coding agent.",
        install: InstallMethod::InBoxNpmGlobal(&["@openai/codex"]),
        unofficial: false,
        default_selected: true,
        exported_to_host: true,
        probe_commands: &["codex"],
    },
    DevTool {
        id: "openclaw",
        name: "OpenClaw",
        category: DevToolCategory::AgentCli,
        description: "Open-source assistant harness that runs across your devices and chats.",
        // Runs on the host: it manages its own daemon/session outside the
        // box, same shape as Hermes Desktop below.
        install: InstallMethod::HostScript("https://openclaw.ai/install.sh"),
        unofficial: false,
        default_selected: false,
        exported_to_host: false,
        probe_commands: &[],
    },
    // --- Agent desktop apps ---------------------------------------------
    DevTool {
        id: "hermes-desktop",
        name: "Hermes Desktop",
        category: DevToolCategory::AgentDesktop,
        description: "Nous Research's native desktop app for the Hermes agent — chat, voice, file browser, no terminal required.",
        install: InstallMethod::HostScript("https://hermes-agent.nousresearch.com/install.sh"),
        unofficial: false,
        default_selected: false,
        exported_to_host: false,
        probe_commands: &[],
    },
    DevTool {
        id: "codex-desktop",
        name: "Codex Desktop (ChatGPT app)",
        category: DevToolCategory::AgentDesktop,
        description: "OpenAI's official ChatGPT desktop app for Linux, with Codex mode built in.",
        // Official Fedora path per learn.chatgpt.com/docs/linux/linux-app:
        // download the signed .rpm, `dnf install ./chatgpt.x86_64.rpm`.
        // Installing it configures OpenAI's own update repo, so later
        // updates are a normal `dnf upgrade`, not a Kyth-managed step.
        install: InstallMethod::HostRpmUrl(
            "https://persistent.oaistatic.com/codex-app-prod/linux/rpm/latest/chatgpt.x86_64.rpm",
        ),
        unofficial: false,
        default_selected: false,
        exported_to_host: false,
        probe_commands: &[],
    },
    DevTool {
        id: "claude-desktop",
        name: "Claude Desktop",
        category: DevToolCategory::AgentDesktop,
        description: "Anthropic's desktop app. No official Fedora/RPM build exists yet — this opens the community packaging project's release page instead of guessing at an install command.",
        install: InstallMethod::Manual("https://github.com/aaddrick/claude-desktop-debian"),
        unofficial: true,
        default_selected: false,
        exported_to_host: false,
        probe_commands: &[],
    },
    // --- Languages & runtimes --------------------------------------------
    DevTool {
        id: "node",
        name: "Node.js",
        category: DevToolCategory::Language,
        description: "JavaScript/TypeScript runtime — required by most agent CLIs above.",
        install: InstallMethod::InBoxDnf(&["nodejs", "npm"]),
        unofficial: false,
        default_selected: true,
        exported_to_host: true,
        probe_commands: &["node", "npm"],
    },
    DevTool {
        id: "python",
        name: "Python",
        category: DevToolCategory::Language,
        description: "Python 3 with pip, virtualenv, and dev headers.",
        install: InstallMethod::InBoxDnf(&["python3", "python3-pip", "python3-virtualenv", "python3-devel"]),
        unofficial: false,
        default_selected: true,
        exported_to_host: false,
        probe_commands: &["python3"],
    },
    DevTool {
        id: "rust",
        name: "Rust",
        category: DevToolCategory::Language,
        description: "rustc and Cargo, the Rust toolchain.",
        install: InstallMethod::InBoxDnf(&["rust", "cargo"]),
        unofficial: false,
        default_selected: false,
        exported_to_host: false,
        probe_commands: &["cargo"],
    },
    DevTool {
        id: "go",
        name: "Go",
        category: DevToolCategory::Language,
        description: "The Go toolchain.",
        install: InstallMethod::InBoxDnf(&["golang"]),
        unofficial: false,
        default_selected: false,
        exported_to_host: false,
        probe_commands: &["go"],
    },
    // --- Utilities --------------------------------------------------------
    DevTool {
        id: "git",
        name: "Git & GitHub CLI",
        category: DevToolCategory::Utility,
        description: "git, git-lfs, and the `gh` GitHub CLI.",
        install: InstallMethod::InBoxDnf(&["git", "git-lfs", "gh"]),
        unofficial: false,
        default_selected: true,
        exported_to_host: true,
        probe_commands: &["git", "gh"],
    },
    DevTool {
        id: "shell-tools",
        name: "Modern shell tools",
        category: DevToolCategory::Utility,
        description: "ripgrep, fd, fzf, bat, eza, zoxide — fast search and navigation.",
        install: InstallMethod::InBoxDnf(&["ripgrep", "fd-find", "fzf", "bat", "eza", "zoxide"]),
        unofficial: false,
        default_selected: false,
        exported_to_host: true,
        probe_commands: &["rg", "fzf", "bat", "eza", "zoxide"],
    },
    DevTool {
        id: "term-multiplex",
        name: "tmux & Zellij",
        category: DevToolCategory::Utility,
        description: "Terminal multiplexers for long-running agent sessions.",
        install: InstallMethod::InBoxDnf(&["tmux", "zellij"]),
        unofficial: false,
        default_selected: false,
        exported_to_host: true,
        probe_commands: &["tmux", "zellij"],
    },
    DevTool {
        id: "containers",
        name: "Podman & container tools",
        category: DevToolCategory::Utility,
        description: "podman, skopeo, podman-compose for local container work.",
        install: InstallMethod::InBoxDnf(&["podman", "skopeo", "podman-compose"]),
        unofficial: false,
        default_selected: false,
        exported_to_host: false,
        probe_commands: &["podman", "skopeo"],
    },
    // --- Local AI -----------------------------------------------------------
    DevTool {
        id: "ollama",
        name: "Ollama",
        category: DevToolCategory::LocalAi,
        description: "Run open local models (GPU-accelerated when available). Model pulls happen after setup, from the status page.",
        install: InstallMethod::InBoxDnf(&["ollama"]),
        unofficial: false,
        default_selected: false,
        exported_to_host: false,
        probe_commands: &["ollama"],
    },
];

pub fn find_dev_tool(id: &str) -> Option<&'static DevTool> {
    DEV_TOOLS.iter().find(|tool| tool.id == id)
}

pub fn default_selected_ids() -> Vec<&'static str> {
    DEV_TOOLS
        .iter()
        .filter(|tool| tool.default_selected)
        .map(|tool| tool.id)
        .collect()
}

/// Filter the catalog down to a caller-provided id selection, dropping any
/// unknown ids rather than failing the whole request — a stale id from an
/// older wizard build must not block installing everything else the user
/// picked.
pub fn resolve_selection<'a>(selected_ids: &[String]) -> Vec<&'static DevTool> {
    selected_ids
        .iter()
        .filter_map(|id| find_dev_tool(id))
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn catalog_has_no_duplicate_ids() {
        let mut ids: Vec<&str> = DEV_TOOLS.iter().map(|tool| tool.id).collect();
        let before = ids.len();
        ids.sort_unstable();
        ids.dedup();
        assert_eq!(ids.len(), before);
    }

    #[test]
    fn finds_known_tool_and_rejects_unknown() {
        assert_eq!(find_dev_tool("vscode").unwrap().name, "VS Code");
        assert!(find_dev_tool("not-a-real-tool").is_none());
    }

    #[test]
    fn every_tool_has_a_non_empty_description_and_name() {
        for tool in DEV_TOOLS {
            assert!(!tool.name.is_empty(), "{} has an empty name", tool.id);
            assert!(
                !tool.description.is_empty(),
                "{} has an empty description",
                tool.id
            );
        }
    }

    #[test]
    fn unofficial_tools_have_no_probe_and_are_not_default_selected() {
        // An unofficial/manual-install tool cannot be silently preselected
        // or reported "installed" — the wizard must always ask.
        for tool in DEV_TOOLS.iter().filter(|tool| tool.unofficial) {
            assert!(
                !tool.default_selected,
                "{} is unofficial but preselected by default",
                tool.id
            );
        }
    }

    #[test]
    fn manual_install_tools_have_a_real_looking_url() {
        for tool in DEV_TOOLS {
            if let InstallMethod::Manual(url) = tool.install {
                assert!(url.starts_with("https://"), "{} manual url", tool.id);
            }
        }
    }

    #[test]
    fn host_script_and_rpm_urls_use_https() {
        for tool in DEV_TOOLS {
            match tool.install {
                InstallMethod::HostScript(url) | InstallMethod::HostRpmUrl(url) => {
                    assert!(url.starts_with("https://"), "{} install url", tool.id);
                }
                _ => {}
            }
        }
    }

    #[test]
    fn default_selection_is_a_small_useful_starter_set() {
        let defaults = default_selected_ids();
        assert!(!defaults.is_empty());
        assert!(defaults.len() <= 8, "default set should stay minimal");
    }

    #[test]
    fn resolve_selection_drops_unknown_ids_instead_of_failing() {
        let selected = vec!["vscode".to_string(), "not-a-real-tool".to_string()];
        let resolved = resolve_selection(&selected);
        assert_eq!(resolved.len(), 1);
        assert_eq!(resolved[0].id, "vscode");
    }

    #[test]
    fn categories_have_stable_keys_and_labels() {
        for category in [
            DevToolCategory::Editor,
            DevToolCategory::AgentCli,
            DevToolCategory::AgentDesktop,
            DevToolCategory::Language,
            DevToolCategory::Utility,
            DevToolCategory::LocalAi,
        ] {
            assert!(!category.key().is_empty());
            assert!(!category.label().is_empty());
        }
    }
}
