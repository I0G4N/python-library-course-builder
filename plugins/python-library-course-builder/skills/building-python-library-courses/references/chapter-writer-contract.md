# Clean-context chapter writer contract

Use this contract after route design and before authoring learner-facing chapters. It keeps readiness evidence private, gives every chapter an independent writing context, and preserves parent-owned course invariants while allowing natural tutorial prose.

## Contents

- [Separate the four roles](#separate-the-four-roles)
- [Lock the course before writing](#lock-the-course-before-writing)
- [Build a sanitized chapter packet](#build-a-sanitized-chapter-packet)
- [Launch one clean writer per unit](#launch-one-clean-writer-per-unit)
- [Write a tutorial, not a template](#write-a-tutorial-not-a-template)
- [Return one exact fragment](#return-one-exact-fragment)
- [Assemble deterministically](#assemble-deterministically)
- [Review in another clean context](#review-in-another-clean-context)
- [Handle failures without contaminating contexts](#handle-failures-without-contaminating-contexts)

## Separate the four roles

Keep these responsibilities distinct:

1. The **parent author** performs official research and the private readiness preflight, selects the route, fixes the curriculum, and owns all cross-chapter invariants.
2. A **chapter writer** receives one sanitized packet and writes exactly one `lab00`, `prepNN`, or `labNN` fragment.
3. The deterministic **assembler** checks fragment cardinality and parent locks, then orders fragments without rewriting prose.
4. A **whole-course reviewer** reads the assembled course in a separate clean context and reports unit-specific defects.

Do not let a chapter writer choose course scope, diagnose the learner, redesign the Lab graph, change code or tests, or edit another chapter. Never reuse a writer for another unit, even when two chapters look similar.

## Lock the course before writing

The parent author fixes these values before launching any writer:

- ordered unit IDs, concept IDs, outcome IDs, activity IDs, and their mappings;
- selected locale, target version or range, and primary official source set;
- each graded Lab's starter/reference code, public and hidden tests, files, points, and cumulative capstone increment;
- dependencies, one-mainline boundary, teaching-equivalent module cycle, official bridge, target symbols, lower-level primitives, and anti-delegation rules;
- runnable examples that must agree with the code and tests; and
- the exact operational behavior and boundary witnesses the chapter must explain.

Create a lock manifest for the assembler. The manifest orders every expected unit and records the complete JSON Pointer/value set for identity, discriminator, and mapping fields inside the writer-owned `lesson` and `quiz` payloads. A required pointer is any field named `id` or `kind`, or whose name ends in `_id` or `_ids`. This covers concept, outcome, prerequisite, example, trace, question, and choice identities; source and activity mappings; quiz kinds; and the correct-choice mapping. The expected-unit entry itself binds `unit_id`, so do not repeat it as a pointer. Everything outside `tutorial`, `lesson`, and `quiz` remains parent-owned by construction.

The lock set is fail-closed: it must be non-empty and must equal the required pointer set for that fragment shape. Optional collections such as examples and traces contribute required pointers only when present. Build the manifest from the parent-owned course skeleton before launching writers; do not infer expected values from a returned writer fragment.

## Build a sanitized chapter packet

Create a new packet for each unit. Include only what that writer needs:

- unit ID, locale, title, role in the cumulative route, and the previous/next chapter handoff;
- the locked concept, outcome, example, and knowledge-check IDs plus their required mappings;
- the fixed operational contract, concrete trace values, boundary witnesses, code behavior, expected outputs, and capstone increment;
- only the official source excerpts or source facts needed for that chapter, with titles, URLs, version boundary, and guarantee-versus-implementation labels; and
- the required fragment schema and relevant teaching-depth rules.

Never include the learner's raw diagnostic answers, code evidence, readiness summary, route diagnostic questions, capability IDs, capability status, assumed/preparatory decisions, prerequisite profile, or any wording such as “you already know,” “your gap,” or “based on your level.” A prep writer receives the knowledge to teach as ordinary chapter subject matter, not the private reason it was selected.

Do not include another writer's draft or the parent conversation. The packet may state an ordinary curricular dependency such as “the previous chapter established dictionary lookup,” but it must not expose how that dependency was assessed.

## Launch one clean writer per unit

For every expected `lab00`, `prepNN`, and `labNN`, launch a distinct sub-agent with `fork_turns="none"`. Give it only the sanitized packet, the selected-locale teaching example, and the exact output location or return format. Never reuse the same sub-agent for another unit or for a rewrite.

Writers may run in parallel after the parent locks are complete. Preserve the one-writer/one-unit boundary even when batching launches. If the environment cannot create clean-context sub-agents, stop before learner-facing authoring and report the missing capability; do not generate every chapter in the parent's accumulated context.

A writer prompt should say, in substance:

> Write only the assigned unit from the attached packet. Preserve every locked ID and declared observable. Return exactly `unit_id`, `tutorial`, `lesson`, and `quiz`. Write the tutorial as a connected textbook chapter in the selected locale. Do not mention diagnostics, readiness, learner level, profiles, capabilities, or authoring machinery.

## Write a tutorial, not a template

Make `tutorial` the full learner-facing Markdown chapter. Use headings where they improve navigation, but let the subject determine the narrative. Do not repeat a fixed heading inventory merely to mirror schema fields, and do not enforce a word-count target.

Develop the explanation slowly enough that the learner can predict the program:

- open with the concrete project problem and connect it to the cumulative product;
- define every professional term at first use in plain language, then immediately show why it matters here;
- carry the same real input or state through each relevant intermediate representation, type, shape, ownership transfer, or lifecycle transition;
- explain not only what the code does, but why the behavior follows, which public contract supports it, and which nearby mental model would be wrong;
- execute a normal case and a boundary case, connect wrong code to symptom and cause, apply the recovery, and show the corrected observable; and
- lead naturally into the knowledge check and, for graded Labs, the coding/capstone increment.

Use the structured `lesson` as a sidecar that preserves concepts, outcomes, contracts, traces, mappings, and source claims for validation. Its facts must be visible and explained in `tutorial`; do not render the sidecar as a rigid learner-facing card sequence. Keep quiz prompts and feedback specific to the same concrete value flow.

Length follows the subject. A short chapter is acceptable only when it completely explains its mechanism, terminology, trace, boundary, and application. A long chapter still fails if it is repetitive, generic, or merely expands an authoring checklist.

## Return one exact fragment

Each writer returns one UTF-8 JSON object with exactly four top-level fields:

```json
{
  "unit_id": "lab01",
  "tutorial": "# A natural tutorial chapter\n\n...",
  "lesson": {
    "concepts": [],
    "outcomes": []
  },
  "quiz": []
}
```

`tutorial` is non-empty Markdown, `lesson` is the complete structured sidecar required by the curriculum contract, and `quiz` is the complete knowledge-check array. Do not return sources, code, tests, files, dependencies, module-cycle metadata, bridge metadata, readiness data, or commentary alongside the fragment.

## Assemble deterministically

Create a parent lock manifest such as:

```json
{
  "schema_version": 1,
  "expected_units": [
    {
      "unit_id": "lab01",
      "locked": {
        "/lesson/concepts/0/id": "lab01.c-parser",
        "/lesson/outcomes/0/id": "lab01.o-trace",
        "/quiz/0/id": "lab01.k-trace",
        "/quiz/0/kind": "execution_trace",
        "/quiz/0/choices/0/id": "a",
        "/quiz/0/choices/1/id": "b",
        "/quiz/0/choices/2/id": "c",
        "/quiz/0/answer_id": "b",
        "/quiz/0/concept_ids": ["lab01.c-parser"],
        "/quiz/0/outcome_ids": ["lab01.o-trace"]
      }
    }
  ]
}
```

Place writer fragments in a dedicated directory, then run:

```bash
uv run --cache-dir "${TMPDIR:-/tmp}/coursekit-skill-uv-cache" --python 3.13 --no-project python "$SKILL_DIR/scripts/assemble_chapter_fragments.py" /path/to/chapter-locks.json /path/to/fragments --output /tmp/assembled-chapters.json
```

The assembler requires exactly one JSON fragment for every expected unit, emits units in manifest order, and rejects missing, duplicate, or unexpected units. It rejects empty locks, missing required locks, pointers outside the derived identity/mapping allowlist, extra top-level fields, and any value that differs from its parent-owned lock. A pointer for an optional item that the writer removed is also rejected, so omission cannot silently weaken a parent lock. Treat every rejection as an authoring failure; never weaken or remove a parent lock to accept a writer's drift.

Merge the validated fragments into the parent-owned course skeleton without changing sources, code, tests, files, points, dependencies, module cycles, bridges, or the capstone graph. Validate the complete specification after the merge.

## Review in another clean context

After assembly, launch one new whole-course reviewer with `fork_turns="none"`. Give it the assembled learner-visible chapters, parent locks, official claims, code/test observables, and the authoring rubric. Do not give it readiness evidence, writer conversations, or the intended review result.

Require the reviewer to check:

- natural textbook progression and first-use definitions of professional terms;
- one mainline per graded Lab, cumulative continuity, and correct official bridges;
- tutorial/sidecar/quiz/code/test agreement for every concrete value and boundary;
- absence of learner-facing readiness, diagnostic, profile, capability, and authoring metadata; and
- enough explanatory depth that a locked knowledge check does not leave the reading surface thin.

The reviewer reports findings by unit ID and lock or rubric rule. It does not rewrite chapters itself.

## Handle failures without contaminating contexts

For each rejected fragment or reviewer finding, create a replacement sanitized packet containing the original locked packet plus only the concrete defect and required observable. Launch a new clean-context writer with `fork_turns="none"`; never ask the original writer or whole-course reviewer to repair the prose.

Replace the failed fragment, rerun the assembler, and rerun a new clean whole-course review. Continue until every expected fragment passes its locks and the assembled course passes the semantic review. Keep temporary packets, fragments, locks, and reports outside the generated learner repository.
