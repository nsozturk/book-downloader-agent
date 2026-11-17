# MISTAKES

## 001 — claimed that qpdf removes active content from a PDF (2026-11-17)

**Context:** Design proposal for the `bookdl release` command, in chat.
**What I did:** I told the user that `qpdf` rebuilds a PDF "without active elements" (JavaScript, launch actions, XFA). I proposed this as step 3 of the plan before I read `qpdf --help=all`.
**Why it was wrong:** qpdf 12.4.2 has no option that removes JavaScript or actions. It only has `--remove-attachment` for embedded files, and `--json` to inspect objects. I described a capability from memory instead of from the tool's help.
**Rule:** Before I name a CLI tool as the way to do a step, run its `--help` and find the exact option. If the option is not there, say "no such option" and propose detect-and-refuse or another tool.
