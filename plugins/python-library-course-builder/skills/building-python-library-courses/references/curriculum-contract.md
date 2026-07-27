# Curriculum contract v4

Schema v4 uses a temporary `route.json` plus one complete package per chapter. The route stores only mechanical/runtime metadata. The parent Agent's Depth Brief remains ephemeral prompt context and is never embedded in the route or generated course.

Existing schema-v2/v3 specifications and generated projects remain compatibility inputs. Do not rewrite or migrate them in place. Explicit regeneration produces a complete new v4 learner/author pair.

## Route shape

```json
{
  "schema_version": 4,
  "course": {
    "id": "pathlib-organizer",
    "curriculum_id": "pathlib-organizer-v4",
    "title": "用 pathlib 构建文件整理器",
    "description": "一条累计、可运行的学习路线。",
    "language": "zh-CN",
    "python_requires": ">=3.13,<3.14",
    "dependencies": [],
    "capstone": "一个可测试的本地文件整理器"
  },
  "target": {
    "name": "pathlib",
    "kind": "stdlib",
    "version": "Python 3.13",
    "track": "core filesystem workflows",
    "official_sources": [
      {
        "id": "python-pathlib",
        "title": "Python 3.13 pathlib documentation",
        "url": "https://docs.python.org/3.13/library/pathlib.html"
      }
    ]
  },
  "research": {
    "status": "complete",
    "version_basis": "Pinned to Python 3.13 documentation.",
    "notes": ["The route uses only documented pathlib behavior."]
  },
  "chapters": [
    {
      "id": "lab00",
      "title": "环境与学习循环",
      "kind": "orientation",
      "depends_on": null,
      "study_minutes": {"min": 15, "max": 30},
      "sources": ["python-pathlib"],
      "owned_paths": [],
      "task_contracts": []
    },
    {
      "id": "lab01",
      "title": "路径值与文件系统边界",
      "kind": "lab",
      "depends_on": "lab00",
      "study_minutes": {"min": 30, "max": 45},
      "sources": ["python-pathlib"],
      "owned_paths": [
        "src/pathlib_organizer/paths.py"
      ],
      "task_contracts": [
        {
          "id": "lab01.q1",
          "title": "实现 normalize_path",
          "file": "src/pathlib_organizer/paths.py",
          "symbol": "normalize_path",
          "prompt": "实现讲义中的路径规范化边界。",
          "points": 10,
          "timeout_seconds": 30,
          "public_tests": ["test_paths.py::test_normalize_path"],
          "hidden_tests": ["test_paths.py::test_rejects_empty_path"]
        }
      ]
    }
  ]
}
```

Allowed chapter kinds are `orientation`, `preparatory`, `lab`, `integration`, and `capstone`. IDs and dependencies follow the parent-owned route. `lab00` and preparatory chapters have no task contracts or code/test owned paths. Graded chapters have at least one task.

`owned_paths` are safe, relative, exact final paths. No two chapters own the same path. A task file must be owned by its chapter. Public and hidden selectors refer to files inside that chapter package's respective test directory.

The route does not contain `core_question`, required facts, walkthrough, boundary, design choice, alternative, concepts, outcomes, traces, depth metadata, readiness answers, or prose.

## Chapter package shapes

`tutorial.md` is arbitrary nonempty UTF-8 Markdown. No title, section, keyword, or length is required.

`terms.json` is a presentation-only object:

```json
{
  "terms": [
    {"term": "路径值", "definition": "一个描述位置但不执行 I/O 的值。"}
  ]
}
```

Validation checks only record shape, nonempty strings, and unique term names.

`quiz.json` contains a `questions` array. Each question has a stable `id`, prompt, two or more choices with stable `id` and text, `answer_id` referencing one choice, and optional explanation/feedback. Validation does not inspect topic coverage or answer-position distribution.

Graded packages mirror final owned paths:

```text
starter/src/<package>/...
solution/src/<package>/...
tests/public/...
tests/hidden/...
```

Starter and solution Python files must parse and declare each task's named symbol. Selectors must resolve to collected test functions. The validator does not inspect implementation strategy or prose semantics.

## Learner projection

```text
<slug>/
├── course.toml
├── chapters/<id>/{tutorial.md,terms.json,quiz.json}
├── src/<package>/
├── tests/public/<chapter-id>/...
├── examples/<chapter-id>/...
├── coursekit_runtime/static/
└── .coursekit/course.json
```

Learner quiz files omit answers, explanations, author feedback, solutions, hidden selectors, and hidden tests.

## Author projection

```text
<slug>-author/
├── author.json
├── quiz-answers.json
├── solution/src/<package>/
├── tests/hidden/<chapter-id>/...
└── verification.json
```

`author.json` binds course ID, curriculum ID, and the immutable course contract digest. The local Runner discovers this sibling by default or uses `COURSEKIT_AUTHOR_ROOT`. A mismatch fails closed.

## Readiness and locale

The evidence-based readiness preflight still determines the minimum prerequisite chain. Raw evidence remains temporary. Learner-facing prep is ordinary teaching and contains no diagnostic framing.

The course locale is exactly `zh-CN` or `en`. Localize prose, quiz, feedback, and generated documentation while preserving code, identifiers, commands, API names, and official source titles/URLs.

## Regeneration

Content-prompt or Depth-Brief contract changes may recall chapter Writers. Runtime, Web, verifier, or exporter changes must only re-export or revalidate existing v4 packages.

`regenerate_course.py chapter COURSE --chapter <id> --reason ... --json REQUEST`
recalls only the named Writer with the fixed route, facts, task IDs, public
interfaces, and owned paths. All other chapter packages remain byte-identical.
Selectors in `REQUEST` are package-relative and task examples use the original
nested package shape. The request does not reconstruct semantic teaching
context from old prose: it explicitly requires the parent Agent to supply a new
ephemeral Depth Brief.

After the rebuilt learner/author candidate passes acceptance, bind the request
to that candidate:

```bash
regenerate_course.py check COURSE --candidate-course CANDIDATE \
  --chapter-request REQUEST --json PLAN
regenerate_course.py apply COURSE --candidate-course CANDIDATE \
  --plan PLAN --confirm-stopped --accept-replacement --json RESULT
```

Targeted check allows only the named chapter's `tutorial.md`, `terms.json`,
`quiz.json`, owned source files, public/hidden tests, examples, and the derived
binding/receipt files to change. Other chapter artifacts and unrelated material
files must be byte-identical. It validates the candidate receipt offline;
targeted apply stages the old learner/author roots in one transient rollback
directory, restores both originals together on handled pre-cleanup failures
while their bound paths remain intact, and records zero Writer calls during
apply. Path interference fails closed. After successful post-swap validation,
it deletes the previous pair and rollback directory and retains no backup.
Partial cleanup failure keeps the verified new pair installed and reports
possible partial residue; a successful replacement is irreversible.
