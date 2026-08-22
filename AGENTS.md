# Repository publishing workflow

- Never open a pull request for this repository.
- Commit approved changes directly to the `testing` branch and push them to `origin/testing`.
- `testing` is the default working branch. `main` is the stable promotion target only.
- New Cloud Agents must open on `github.com/mrtrick37/kyth` at `testing`, not `main`.
- If this session checked out `main` (or any other branch) and the user did not explicitly ask to work on that branch or to promote to stable, switch to `testing` before making changes:

      git fetch origin testing
      git checkout testing
