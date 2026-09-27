# OpenSSF Best Practices: Passing Reporting Evidence

This document maps the OpenSSF Best Practices Passing reporting criteria for
KythOS to project evidence. It is intended to support the badge entry at
bestpractices.dev and to keep the justifications reviewable in the repository.

The response-rate criteria use the badge window of reports submitted from 2 to
12 months before the review date. For the June 16, 2026 review, that window is
June 16, 2025 through April 16, 2026.

## Bug-Reporting Process

### `report_process`

Recommended status: Met

Recommended URL: `https://github.com/kyth-os/kyth/issues`

Recommended entry: KythOS accepts public bug reports through GitHub Issues. The
repository provides structured issue templates for installer problems, system
regressions, hardware compatibility, gaming compatibility, and feature
proposals. The README links directly to "Report a Bug".

Evidence:

- `README.md` links to GitHub Issues as the public bug-reporting path.
- `.github/ISSUE_TEMPLATE/` contains focused report templates.
- `.github/ISSUE_TEMPLATE/config.yml` disables blank issues and directs
  security reports to private advisories.

### `report_tracker`

Recommended status: Met

Recommended entry: KythOS uses GitHub Issues to track individual public bug
reports, compatibility reports, regressions, installer problems, and feature
proposals.

Evidence:

- Public tracker: `https://github.com/kyth-os/kyth/issues`
- Issue templates assign actionable titles and labels where appropriate.

### `report_responses`

Recommended status: Met

Recommended entry: In the June 16, 2025 through April 16, 2026 badge window,
the public GitHub tracker had 9 non-PR issues. All 9 were acknowledged by being
maintainer-authored, closed, or commented on by the maintainer, so the project
acknowledged a majority of public bug reports in the required 2-12 month window.

Evidence snapshot from the GitHub Issues API on June 16, 2026:

| Issue | Created | Status | Evidence |
| --- | --- | --- | --- |
| `#3` | 2026-03-06 | Closed | Maintainer-authored and closed |
| `#4` | 2026-03-06 | Closed | Maintainer-authored and closed |
| `#5` | 2026-03-06 | Closed | Maintainer-authored and closed |
| `#6` | 2026-03-06 | Closed | Maintainer-authored and closed |
| `#7` | 2026-03-06 | Closed | Maintainer-authored and closed |
| `#8` | 2026-03-06 | Closed | Maintainer-authored and closed |
| `#9` | 2026-03-06 | Closed | Maintainer-authored and closed |
| `#10` | 2026-03-06 | Closed | Maintainer comment on 2026-04-01 |
| `#50` | 2026-03-18 | Closed | Maintainer comment on 2026-04-01 |

### `enhancement_responses`

Recommended status: Met

Recommended entry: KythOS uses GitHub Issues for enhancement requests and has a
dedicated feature proposal template. In the June 16, 2025 through April 16,
2026 badge window, the identifiable enhancement-style public issue was `#50`;
it was closed and received a maintainer comment on April 1, 2026. No public
external enhancement requests were left unacknowledged in that window.

Evidence:

- `.github/ISSUE_TEMPLATE/feature.yml` is the enhancement request template.
- `#50` was closed and commented on by the maintainer.

### `report_archive`

Recommended status: Met

Recommended URL: `https://github.com/kyth-os/kyth/issues`

Recommended entry: GitHub Issues and Discussions provide public, searchable,
URL-addressable archives for reports and responses. Issue templates direct
questions and support discussions to GitHub Discussions and actionable defects
to GitHub Issues.

Evidence:

- Issues archive: `https://github.com/kyth-os/kyth/issues`
- Discussions archive: `https://github.com/kyth-os/kyth/discussions`
- `.github/ISSUE_TEMPLATE/config.yml` links both reporting paths.

## Vulnerability Report Process

### `vulnerability_report_process`

Recommended status: Met

Recommended URL: `https://github.com/kyth-os/kyth/security/policy`

Recommended entry: KythOS publishes its vulnerability reporting process in
`SECURITY.md`, which GitHub exposes at the repository Security Policy URL. It
asks reporters not to open public issues, identifies the private report form,
lists information to include, and describes triage and disclosure handling.

Evidence:

- `SECURITY.md`
- GitHub Security Policy: `https://github.com/kyth-os/kyth/security/policy`

### `vulnerability_report_private`

Recommended status: Met

Recommended URL: `https://github.com/kyth-os/kyth/security/advisories/new`

Recommended entry: KythOS supports private vulnerability reports through
GitHub's private vulnerability reporting form and links that form from
`SECURITY.md` and the issue template contact links.

Evidence:

- `SECURITY.md` links `https://github.com/kyth-os/kyth/security/advisories/new`
- `.github/ISSUE_TEMPLATE/config.yml` routes security reports to the same
  private advisory form.

### `vulnerability_report_response`

Recommended status: N/A

Recommended entry: No KythOS vulnerability reports were received in the last six
months as of the June 16, 2026 review. If a report is received, `SECURITY.md`
commits the project to acknowledge it within seven days, which is stricter than
the OpenSSF Passing requirement of 14 days.

Evidence:

- `SECURITY.md` documents a seven-day acknowledgement target.
- No public advisory or vulnerability report required initial response timing in
  the last six months at the time this evidence was added.
