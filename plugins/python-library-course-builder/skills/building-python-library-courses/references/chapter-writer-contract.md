# Chapter Writer contract v4

This contract governs the parent Agent and the one Writer assigned to each chapter. It deliberately separates content depth from machine validation.

## Parent ownership

Before any Writer starts, the parent fixes:

- course locale, pinned target version, track, official sources, and chapter order;
- one core question and one cumulative project increment per chapter;
- 3–6 required official facts and their guarantee-versus-implementation status;
- component responsibility, dependency direction, and the caller-visible interface;
- one concrete walkthrough case and one boundary case with symptom and recovery;
- the chosen design, one credible alternative, and the reason for the choice;
- stable task IDs, file paths, symbols, points, timeouts, test selectors, and non-overlapping owned paths; and
- concise previous/next handoffs.

The parent records these in an ephemeral Depth Brief:

```text
chapter_id
chapter_kind
core_question
project_increment
required_facts
interface_boundary
walkthrough_case
boundary_case
design_choice
credible_alternative
previous_handoff
next_handoff
official_sources
task_contracts
owned_paths
```

The brief is not part of schema v4, the generated course, the Web API, progress state, or verification receipt. Do not add a score, band, length range, concept/outcome mapping, trace schema, readiness evidence, or another chapter's prose.

## One complete package per Writer

Launch one fresh `fork_turns="none"` Writer per chapter. The Writer owns only:

```text
packages/<chapter-id>/
├── tutorial.md
├── terms.json
├── quiz.json
├── starter/src/...       # graded chapter only
├── solution/src/...      # graded chapter only
├── tests/public/...      # graded chapter only
├── tests/hidden/...      # graded chapter only
└── examples/...          # optional
```

The same Writer produces prose, quiz, code, and tests so they share one case and one behavior boundary. `lab00` and `prepNN` produce no starter, solution, code tests, points, or submissions.

The Writer may choose any Markdown headings, narrative order, and chapter length. `tutorial.md` is the only prose source of truth. `terms.json` only supplies the Web terminology rail; it is not proof that the body uses or covers each term.

## Writer prompt

This section is the canonical content prompt contract. Give the Writer this instruction, localized to the chosen course language:

> Write a natural, connected textbook chapter rather than a field manual. Organize it around the core question and carry the walkthrough case through the complete mechanism. Naturally explain the essential definitions, component responsibilities, caller/implementer interface, data or control flow, selected design, one credible alternative, benefits and costs, and the boundary case's symptom, cause, and recovery. Choose headings and length for the subject. Keep the quiz, code, and tests on the same case and behavior boundary.

Do not provide a complete teaching example, other chapters' full text, depth score, prose band, word range, large rubric, raw readiness answer, capability status, or concept/outcome/trace mapping.

## Silent single-call self-review

In the same call, the Writer:

1. designs a natural narrative around the core question;
2. writes the complete package;
3. silently checks whether a learner can:
   - define the mechanism and its purpose;
   - predict every step of the walkthrough case;
   - identify component responsibility, dependency direction, and interface;
   - explain the selected design versus the credible alternative;
   - state the main benefit, cost, and invariant;
   - diagnose and recover from the boundary case; and
   - complete the coding task from the chapter;
4. revises any insufficient part before returning; and
5. emits only final files, never a checklist, score, critique, or chain of thought.

This is a prompt-quality promise. No downstream script tries to prove semantic completeness.

## Mechanical repair

Assembly may reject only:

- mismatched chapter/task IDs;
- missing or unparseable required files;
- an invalid quiz answer reference;
- conflicting, escaping, absolute, or symlinked owned paths;
- invalid Python syntax;
- a missing test selector or declared symbol; or
- answer, solution, hidden-test, or private-selector leakage into the learner projection.

Send the concise error list to the same Writer once. The Writer returns corrected package files only. If the second mechanical check fails, stop and report it. Do not launch a replacement Writer or a whole-course Reviewer.

## Chapter kinds

- `lab00`: setup, course use, and a demonstration of one complete learning loop; it owns no coding task. Do not force architecture analysis.
- `prepNN`: one prerequisite mechanism taught deeply enough to predict the next Lab.
- ordinary `labNN`: one implementable mechanism, its value/control flow, interface, design choice, credible alternative, boundary, and project increment.
- integration/capstone: one end-to-end case composing earlier public interfaces, emphasizing dependency, failure propagation, and system tradeoffs.

Depth means making one mechanism predictable, not adding more topics.
