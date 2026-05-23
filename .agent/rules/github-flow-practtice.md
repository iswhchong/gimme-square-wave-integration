# GitHub Flow and Change Management Rules

You must strictly adhere to the following workflow for all code modifications:
1. Always start by pulling the latest changes (`git pull`) in the terminal.
2. Before modifying any files, create and switch to a descriptive feature or bugfix branch (e.g., `feature/xyz` or `bugfix/abc`). Never work on the main branch.
3. Group your work into small, atomic commits. Use the Conventional Commits format (e.g., `feat: add login validation` or `fix: resolve crash on null value`).
4. Once the task is completed and verified, push the branch and open a Pull Request. Provide a concise summary of your changes in the PR description.
5. Do not merge your own PRs onto the main branch; leave them open for my review.
