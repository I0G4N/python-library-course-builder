# Curriculum contract v2

Use one UTF-8 JSON specification to describe the evidence, teaching route, structured lessons, exercises, and tests. The authoring specification is an input to the Skill. Inside a generated project, the canonical source is the split tree under `platform/course/source/`; its compiler emits the private compiler-generated parity snapshot.

Run the inspector, validator, scaffolder, and verifier through the uv-managed Python 3.13 commands in `SKILL.md`. Schema v2 accepts a course requirement that includes Python 3.13 and excludes Python 3.14. Do not weaken that gate to accommodate the host interpreter.

## Contents

- [Top-level shape](#top-level-shape)
- [Stable identity and evidence](#stable-identity-and-evidence)
- [Structured lesson](#structured-lesson)
- [Knowledge checks](#knowledge-checks)
- [The mechanism and official bridge cycle](#the-mechanism-and-official-bridge-cycle)
- [Coding interfaces](#coding-interfaces)
- [Split canonical source and compilation](#split-canonical-source-and-compilation)
- [Adaptive size](#adaptive-size)

## Top-level shape

The exact field validation lives in `scripts/validate_course.py`. This abbreviated example shows ownership and nesting; authored strings and code must be complete.

```json
{
  "schema_version": 2,
  "course": {
    "id": "pathlib-practice",
    "title": "Practical pathlib",
    "description": "Build a safe local file organizer incrementally.",
    "language": "zh-CN",
    "python_requires": ">=3.13,<3.14",
    "size": "small",
    "dependencies": [],
    "capstone": "A deterministic local file organizer",
    "audience": {
      "level": "basic-python",
      "assumes": ["variables", "functions", "classes", "imports"],
      "does_not_assume": ["pathlib", "filesystem design"],
      "lab_minutes": {"min": 30, "max": 45}
    }
  },
  "target": {
    "name": "pathlib",
    "kind": "stdlib",
    "version": "Python 3.13",
    "breadth": "focused",
    "track": "core filesystem workflows",
    "import_roots": ["pathlib"],
    "official_sources": [
      {
        "id": "python-pathlib",
        "title": "Python 3.13 pathlib documentation",
        "url": "https://docs.python.org/3.13/library/pathlib.html",
        "kind": "documentation",
        "version": "3.13"
      }
    ]
  },
  "research": {
    "status": "complete",
    "version_basis": "Pinned to Python 3.13 documentation.",
    "notes": ["Filesystem effects are graded only under pytest tmp_path."]
  },
  "foundation": {
    "id": "lab00",
    "title": "Lab 00: Python objects, paths, and the test loop",
    "lesson": {"prerequisites": [], "problem": {}, "outcomes": [], "concepts": [], "examples": [], "capstone_bridge": {}, "summary": []},
    "quiz": []
  },
  "labs": []
}
```

## Stable identity and evidence

Course, source, Lab, prerequisite, outcome, concept, example, quiz, choice, and coding-question IDs are stable. Lab IDs are contiguous `lab01` through `labNN`; `depends_on` forms one linear chain starting at `lab00`. The `course.audience` object is mandatory and records the basic-Python assumptions plus the 30-45 minute Lab budget.

Every official source is a primary HTTPS source with a title and applicable version or revision. Concepts cite registry IDs through `source_claims`, never an unregistered free-form URL. Each claim is marked `documented` for a public contract or `implementation` for a version-pinned implementation observation. Do not turn an implementation detail into a promised API.

`target.import_roots` lists the top-level Python packages whose use is controlled by the mechanism cycle. Third-party targets require pinned or bounded PEP 508 dependencies. Standard-library courses may leave dependencies empty.

## Structured `lesson`

Lab 00 and every graded Lab use the same `lesson` object:

```json
{
  "prerequisites": [
    {
      "id": "lab01.p-functions",
      "title": "Functions and return values",
      "why": "The exercise exposes behavior through one function boundary.",
      "refresh": "A function receives owned inputs and returns an explicit result."
    }
  ],
  "problem": {
    "context": "The organizer needs to represent a root and child safely.",
    "naive_approach": "Concatenate strings with a slash.",
    "failure": "Separators, path kinds, and filesystem effects become conflated."
  },
  "outcomes": [
    {"id": "lab01.o-trace", "text": "Trace input, operation, and output ownership."},
    {"id": "lab01.o-diagnose", "text": "Explain and repair one broken boundary."}
  ],
  "concepts": [
    {
      "id": "lab01.c-path-model",
      "name": "Lexical path composition",
      "definition": "A path object describes a path without necessarily performing I/O.",
      "purpose": "It separates representation from filesystem effects.",
      "mechanism": ["Validate the pieces.", "Create a new value.", "Return it without touching disk."],
      "mental_model": "Treat a path as a recipe, not an already-created file.",
      "design_reasons": ["A value object makes effects explicit."],
      "benefits": ["Composition is testable without creating files."],
      "tradeoffs": ["A later explicit I/O step is still required."],
      "invariants": ["Composition alone performs no filesystem write."],
      "boundaries": ["Platform normalization may differ."],
      "pitfalls": ["Do not infer existence from a composed path."],
      "source_claims": [
        {"source_id": "python-pathlib", "claim": "Path exposes lexical composition operations.", "status": "documented"}
      ]
    }
  ],
  "examples": [
    {
      "id": "lab01.e-run",
      "title": "Compose one child",
      "kind": "runnable",
      "path": "examples/01_compose.py",
      "code": "from pathlib import PurePath\nprint(PurePath('root') / 'a.txt')\n",
      "command": "python examples/01_compose.py",
      "expected_output": "root/a.txt",
      "explanation": "This complete example is CPU/offline runnable.",
      "concept_ids": ["lab01.c-path-model"],
      "outcome_ids": ["lab01.o-trace"]
    },
    {
      "id": "lab01.e-bug",
      "title": "Separate representation from I/O",
      "kind": "diagnostic",
      "wrong_code": "open('root/' + name, 'w')\n",
      "symptom": "A supposedly pure helper creates a file.",
      "cause": "Representation and effect share one hidden operation.",
      "fix_code": "from pathlib import PurePath\ndef target(name):\n    return PurePath('root') / name\n",
      "explanation": "The path follows wrong -> symptom -> cause -> fix.",
      "concept_ids": ["lab01.c-path-model"],
      "outcome_ids": ["lab01.o-diagnose"]
    }
  ],
  "capstone_bridge": {
    "input": "A validated root and child name.",
    "output": "A lexical destination path.",
    "increment": "Add safe target representation to the organizer.",
    "next": "Replace the hand-built representation boundary with the official Path API."
  },
  "summary": ["Representation is distinct from effect.", "The next Lab grades the official bridge."]
}
```

Every lesson is written for a learner with basic Python only and supports 30-45 minutes of focused work. Each concept must define the term, explain its purpose and mechanism, give a mental model, justify the design, state benefits and tradeoffs, identify invariants and boundaries, call out pitfalls, and tie claims to evidence.

Every lesson has at least two examples. One is a complete runnable file with an exact command and expected output. One is a diagnostic with wrong code, visible symptom, root cause, and fixed code: wrong -> symptom -> cause -> fix. Accelerator-only surfaces use metadata, configuration, source traces, or preflight examples; mandatory examples and grading stay CPU/offline runnable.

For a runnable example whose lesson-relative file is `{path}`, the command is exactly `python {path}`. Shell wrappers, `python -m`, chained commands, alternate interpreters, and extra flags are outside this deterministic example contract.

The rule against prerequisite leakage is strict: a prerequisite may refresh only material actually introduced in an earlier Lab. New syntax, framework concepts, and mathematics belong in the current lesson's open definitions and runnable trace. Every exact formula graded by public or hidden tests needs a worked numeric derivation visible before the exercise.

The cumulative capstone must carry meaningful values through the promised route. A stage-name-only tuple, callback log, or fake plumbing trace is not integration. Capstone tests perturb identities, masks, values, configuration branches, and ordering so bypassing an earlier responsibility fails observably.

## Knowledge checks

Each Lab, including Lab 00, has both an execution-trace and a diagnostic question. A question has:

- a stable ID and `kind` (`execution_trace` or `diagnostic`);
- a prompt and explanation;
- three or four choices with stable IDs, text, and misconception-specific feedback;
- `answer_id`, which references one choice ID rather than a numeric array position;
- `concept_ids` and `outcome_ids` that resolve inside the same lesson.

Use every available answer position across the whole course; no position may hold more than 40% of correct answers. Choice order is authored data and must stay stable through compilation. Learner-facing GET responses redact `answer_id` and all unselected feedback. An answer POST returns correctness and only the selected feedback plus the post-answer explanation allowed by the progression contract.

## The mechanism and official bridge cycle

Every graded Lab declares `module_cycle.reimplementation`:

```json
{
  "module_cycle": {
    "reimplementation": {
      "module_id": "lab01.mini-path",
      "title": "Teaching-equivalent path value",
      "target_symbols": ["pathlib.PurePath"],
      "lower_level_dependencies": ["strings", "tuples", "dataclasses"],
      "learner_file": "lab01/mini_path.py",
      "question_ids": ["lab01.q1"],
      "forbidden_imports": ["pathlib"]
    }
  }
}
```

The reimplementation is a teaching-equivalent: it reveals one mechanism with lower-level primitives and explicitly omits production breadth and optimization. Both starter and reference implementations must avoid target import roots and the declared forbidden imports.

Lab 01 has no official bridge. Every later Lab starts with a graded `official_bridge` coding question for the mechanism handwritten in the previous Lab:

```json
{
  "official_bridge": {
    "from_lab": "lab01",
    "mini_module": "lab01.mini_path",
    "official_symbols": ["pathlib.PurePath"],
    "required_imports": ["pathlib"],
    "question_id": "lab02.q1",
    "observables": [{"id": "parts", "description": "The ordered path components."}],
    "comparison_cases": [
      {"input": "official_parts('root/a.txt')", "expected": ["root", "a.txt"], "observable_ids": ["parts"]}
    ]
  }
}
```

The bridge question is first, has `kind: "official_bridge"`, imports the pinned target API, and makes its declared observables testable. The same Lab then contains at least one `reimplementation` question for the next mechanism. The `mini_module` is comparison metadata only: no downstream starter, reference, public/hidden test, or capstone may import a prior mini implementation. When a previous capability is needed, the current lesson teaches the official API call directly.

The next bridge's `official_symbols` is responsibility-complete: as a v2 baseline, its set exactly equals the immediately previous reimplementation's `target_symbols`. Every declared `required_imports` root appears directly in both starter and reference bridge files. Every `reimplementation` question points to the declared `learner_file`; that file and its reachable declared helpers reject target roots, prior-Lab helpers, prior mini modules, aliased imports, and literal `importlib.import_module(...)` or `__import__(...)` delegation.

The bridge belongs in the immediately next Lab and covers every conceptual responsibility named by the previous Lab's reimplementation questions and target symbols. Metadata, lesson comparison, official calls, observables, comparison cases, and tests must all describe that same mechanism.

## Coding interfaces

Each graded Lab contains one to three coding questions. Every question declares a stable ID, `kind`, title, learner file, symbol, prompt, positive points, timeout from 1 through 90 seconds, concept/outcome mappings, one worked input/output explanation, and public plus hidden test selectors. Starter and reference code both declare the named symbol.

`files[].path` is a POSIX path rooted under its Lab. Reject absolute paths, backslashes, `..`, Windows-reserved names, duplicate paths, unresolved tokens, syntax errors, and cross-Lab destinations. Public and hidden tests are valid Python, define their selector, and cannot conflict when shared by questions.

The compiler emits a learner-safe `source_policy` for every coding question. Its fields are `local_root`, `required_imports`, `forbidden_imports`, `prior_mini_modules`, and `forbidden_course_roots`. This is generated metadata, never an author-supplied escape hatch. Learner question objects use an explicit public allowlist; unknown authoring fields are rejected and cannot flow into the learner manifest.

Reference code is a clean solution, not a patched starter. Hidden tests add boundary, invalid-input, mutation, ordering, anti-delegation, and cleanup cases; they do not redefine the public contract. Points are the sum of declared questions, never a fixed course total.

## Split canonical source and compilation

The scaffolder writes a human-reviewable source tree:

```text
platform/course/source/
├── course.json
├── sources.json
├── foundations/
│   ├── lesson.json
│   ├── quiz.json
│   └── examples/*.py
└── labs/labNN/
    ├── lab.json
    ├── lesson.json
    ├── examples/*.py
    ├── starter/**
    ├── reference/**
    └── tests/{public,hidden}/**
```

There is no editable `source/authoring-spec.json`. The compiler independently validates direct split-source edits, renders a complete Markdown fallback, preserves the reconstructable `lesson_outline`, and emits `compiled/authoring-spec.json` as a private compiler-generated parity snapshot. Scaffolding then checks that snapshot is structurally equal to the validated input specification.

A schema-v2 semantic rewrite uses a new incompatible `curriculum_id` ending in `-v2` and does not list v1 as compatible. This resets learner progress intentionally. Do not automatically bump progress-state `version`, artifact-index `schema_version`, `engine_version`, or `layout_version`; those are separate runtime contracts.

## Adaptive size

- `small`: 3-5 graded Labs.
- `medium`: 6-8 graded Labs.
- `large`: select one coherent track first, then 6-10 graded Labs.

Count public capabilities and product surfaces before choosing. Every selected route must fit one environment and one cumulative capstone. If a broad target still has multiple plausible tracks, stop before creating files and ask for the one material choice.
