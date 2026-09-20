# Provenance — skill-creator repository capture

Purpose: reference capture of Anthropic's `skill-creator` skill repository,
so Peter and the agent can study it when designing their own equivalent
`/author-sc`. No design of `/author-sc` was performed here. Do not commit or
push without Peter's direction.

- Source repository: `https://github.com/anthropics/skills.git`
- Upstream subtree: `skills/skill-creator`
- Upstream commit: `34040c9c568585f6929bedeaad110ad08f079624`
  (main, 2026-09-10 12:44:08 -0700, "Update claude-api skill: Managed Agents
  `auto` permission policy and `ant beta:sessions connect` (#1750)")
- Capture date: 2026-09-20
- Capture method: sparse checkout of the subtree, then byte-for-byte
  replacement of individual files with versions Peter pasted in chat from
  his Claude Code-bundled copy of the skill.

## Which bytes are which

Files pasted by Peter (Claude Code-bundled versions) OVERWROTE the sparse
checkout copies. The directory is therefore a hybrid: most files are exact
upstream bytes, a few are Peter's bundled variants. The table below records
the per-file status as of 2026-09-20, verified by `diff` against the
upstream commit above.

| File | Status vs upstream 34040c9 | Notes |
|---|---|---|
| LICENSE.txt | DIFFERS | Peter pasted the vanilla Apache 2.0 template (first line `Apache License`); upstream has an Anthropic-modified header (leading blank line, centered title, `Copyright 2026 Anthropic, PBC.`, no trailing newline). |
| SKILL.md | DIFFERS | Pasted by Peter; matches upstream except 3 lines in "Package and Present" (file-delivery tool framing: `present_files` / `SendUserFile` / Save-skill button vs upstream's `present_files`-only wording). |
| agents/analyzer.md | IDENTICAL | |
| agents/comparator.md | IDENTICAL | Captured copy had a stray final sentence (`If truly equal, declare a TIE.`) that matched neither Peter's paste nor upstream; removed 2026-09-20. |
| agents/grader.md | IDENTICAL | |
| assets/eval_review.html | IDENTICAL | |
| eval-viewer/generate_review.py | IDENTICAL | Preserves Peter's supplied `--previous-feedback` (docstring) vs `--previous-workspace` (argparse) mismatch, and the `dict[str, dict]` annotation in `main()` — both verbatim from his paste. |
| eval-viewer/viewer.html | DIFFERS | 1-line comment difference: paste says `// feedback will be downloaded on submit`; upstream says `// feedback will be downloaded on final submit`. Two earlier transcription defects fixed 2026-09-20 (restored `\u2713`/`\u2717` escapes; restored `metadata.timestamp +` in the timestamp line). |
| references/schemas.md | IDENTICAL | |
| scripts/__init__.py | IDENTICAL | Never pasted; pure sparse-checkout bytes. |
| scripts/aggregate_benchmark.py | IDENTICAL | |
| scripts/generate_report.py | IDENTICAL | `\u2014` escape in `title_prefix` preserved verbatim from paste. |
| scripts/improve_description.py | IDENTICAL | One transcription slip caught and corrected 2026-09-20 (false-triggers loop body). |
| scripts/package_skill.py | IDENTICAL | |
| scripts/quick_validate.py | DIFFERS | Peter's bundled version is NEWER than upstream at this commit: it adds the single-SKILL.md check (`EXCLUDED_DIR_PARTS`, `_counts_as_skill_md`) which upstream 34040c9 lacks. |
| scripts/run_eval.py | IDENTICAL | One transcription slip caught and corrected 2026-09-20 (duplicated `--timeout` argument). |
| scripts/run_loop.py | IDENTICAL | |
| scripts/utils.py | IDENTICAL | |

## Related exemplar

Peter's original paste of the Claude Code-bundled SKILL.md (an earlier
variant, differing from both upstream and the repo copy above — e.g.
`"perfect, love this"` feedback example, `""` in the bundled one;
`"Extract text from PDF"` vs `"Extract this text from PDF"`) is kept
verbatim, with a provenance header, at:

- `~/workspace/dsys/doc/exemplars/skill-creator.md` (491 lines)

So there are three SKILL.md variants on record: (1) the bundled original at
`exemplars/skill-creator.md`, (2) upstream 34040c9 bytes, (3) Peter's new
paste in `skill-creator-repo/SKILL.md` (upstream + evolved "Package and
Present" section).

## Hashes

`SHA256SUMS` in this directory holds SHA-256 hashes of every file,
generated 2026-09-20 after all corrections.
