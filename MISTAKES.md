# MISTAKES

## 001 — claimed that qpdf removes active content from a PDF (2026-11-17)

**Context:** Design proposal for the `bookdl release` command, in chat.
**What I did:** I told the user that `qpdf` rebuilds a PDF "without active elements" (JavaScript, launch actions, XFA). I proposed this as step 3 of the plan before I read `qpdf --help=all`.
**Why it was wrong:** qpdf 12.4.2 has no option that removes JavaScript or actions. It only has `--remove-attachment` for embedded files, and `--json` to inspect objects. I described a capability from memory instead of from the tool's help.
**Rule:** Before I name a CLI tool as the way to do a step, run its `--help` and find the exact option. If the option is not there, say "no such option" and propose detect-and-refuse or another tool.

## 002 — pushed a commit with a failing test (2026-11-17)

**Context:** Commit `41aa8e8` on `security-hardening`. I removed the unused parameter `extra_ro` from `tool_command` in `bookdl/viewer.py`.
**What I did:** I ran the tests, the commits and the push in one shell command. The test run was joined to the next step with `;` and its output went through `grep`, so a failure did not stop the chain. One test still passed four arguments to `tool_command` and failed with `TypeError`. The commit and the push went out anyway.
**Why it was wrong:** I searched the tests for the name `extra_ro`, but the test passed the argument by position, so the search found nothing. Then nothing gated the commit on the test result.
**Rule:** Run the test suite as its own step and read the result before `git commit`. If tests and commit are in one command, join them with `&&` and do not pipe the test run through a filter that hides its exit code. When I remove a parameter, search for the calls of the function, not for the parameter name.
