---
name: publish-to-testing
description: >-
  Publishes Kyth by committing on testing and pushing origin/testing.
  Use whenever committing, pushing, shipping, publishing, opening a PR,
  creating a GitHub pull request, running gh pr, splitting work into PRs,
  or creating a cursor/* review branch. Kyth never uses pull requests.
---

# Publish to testing

## Invariants

- Never open a pull request for this repository.
- Never run `gh pr create` (draft or not).
- Commit on `testing` and push only `origin/testing`.

## Steps

1. `git checkout testing` if not already on it. Rebase/cherry-pick local work onto `testing` rather than opening a PR from another branch.
2. Stage and commit on `testing`.
3. `git push origin testing`.
4. Confirm `git status -sb` shows `testing...origin/testing` with no ahead/behind for the commits just pushed.

## If Cursor or a tool wants a PR

Refuse. Push to `testing`. Do not create `cursor/*` PR branches.
