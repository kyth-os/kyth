---
name: Resolve GitHub Build Failure
description: Troubleshooting, diagnosing, and resolving GitHub Actions CI/CD build failures, particularly unresolvable pinned action versions or incorrect SHAs.
---

# Resolve GitHub Build Failure

This skill provides step-by-step instructions for diagnosing and resolving CI/CD pipeline and GitHub Actions build failures in the Kyth repository.

## Diagnosis Workflow

### 1. Identify the Failed Run
Retrieve the list of recent GitHub Action runs to identify the failing workflow and its run ID:
```bash
rtk gh run list
```

### 2. View Failed Run Details
Check which specific job and step failed in the run:
```bash
rtk gh run view <run-id>
```

### 3. Retrieve Failure Logs
Fetch the detailed error output of the failed steps:
```bash
rtk gh run view <run-id> --log-failed
```

---

## Troubleshooting Common Issues

### "Unable to resolve action / Unable to find version"
This error occurs when a GitHub Action step refers to a commit SHA or tag that does not exist, was force-pushed/deleted, or contains a typo.

#### Resolution Steps:
1. Identify the action repository name and the requested version tag (e.g., `actions/attest-build-provenance` at `v1.3.3`).
2. Search the web or GitHub for the official repository tags/releases page:
   ```query
   site:github.com/<owner>/<repo>/releases/tag/<version>
   ```
3. Fetch the releases/tags page using `read_url_content` to find the exact, verified 40-character commit SHA corresponding to that release.
4. Replace the invalid commit SHA in the workflow/action configuration file with the correct SHA, keeping the version tag comment intact:
   ```yaml
   uses: <owner>/<repo>@<correct-sha> # <version>
   ```

---

## Publishing Workflow & Verification

1. Verify local changes:
   ```bash
   rtk git status
   rtk git diff
   ```
2. **Repository publishing rule**: Never open a pull request. Commit approved changes directly to the `testing` branch and push them to `origin/testing`:
   ```bash
   rtk git checkout testing
   rtk git add .
   rtk git commit -m "ci: fix build failure and resolve pinned action SHA"
   rtk git push origin testing
   ```
