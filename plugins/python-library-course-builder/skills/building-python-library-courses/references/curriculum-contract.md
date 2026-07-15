# Curriculum contract v3

Use one UTF-8 JSON specification to describe a completed readiness decision, ordered preparatory teaching, the formal Lab route, exercises, and tests. Raw learner answers and code evidence remain only in the temporary readiness report. Inside a generated project, the canonical source is the split tree under `platform/course/source/`; its compiler emits the private compiler-generated parity snapshot.

Run the assessor, validator, scaffolder, and verifier through the uv-managed Python 3.13 commands in `SKILL.md`. New authoring uses schema v3 and requires a matching `ready` plan. Schema v2 remains compatibility input. Both schemas require Python 3.13 and exclude Python 3.14.

## Contents

- [Top-level shape](#top-level-shape)
- [Stable identity and evidence](#stable-identity-and-evidence)
- [Assessed readiness and duration](#assessed-readiness-and-duration)
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
  "schema_version": 3,
  "course": {
    "id": "pathlib-practice",
    "title": "用 pathlib 构建本地文件整理器",
    "description": "逐步构建一个可测试的本地文件整理器。",
    "language": "zh-CN",
    "python_requires": ">=3.13,<3.14",
    "size": "small",
    "dependencies": [],
    "capstone": "一个确定、可测试的本地文件整理器",
    "audience": {
      "level": "assessed",
      "prerequisite_profile": {
        "assessment": "evidence-dialogue",
        "route_id": "pathlib-core-route",
        "readiness_summary": "4ac6e2c00d91",
        "capabilities": [
          {
            "id": "python-functions",
            "kind": "python",
            "subject": "Python 函数",
            "title": "定义并调用 Python 函数",
            "status": "known",
            "decision": "assume",
            "basis": "code-evidence",
            "source_ids": ["python-language"],
            "first_used_in": "lab01",
            "preparatory_unit_id": null,
            "preparatory_concept_ids": []
          },
          {
            "id": "path-value-boundary",
            "kind": "library",
            "subject": "路径值与文件系统效果",
            "title": "区分路径表示与文件系统操作",
            "status": "missing",
            "decision": "preparatory",
            "basis": "diagnostic-answer",
            "source_ids": ["python-pathlib"],
            "first_used_in": "lab01",
            "preparatory_unit_id": "prep01",
            "preparatory_concept_ids": ["prep01.c-path-boundary"]
          }
        ]
      }
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
        "id": "python-language",
        "title": "Python 3.13 tutorial",
        "url": "https://docs.python.org/3.13/tutorial/",
        "kind": "documentation",
        "version": "3.13"
      },
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
  "preparatory_units": [
    {
      "id": "lab00",
      "title": "Lab 00：环境与学习流程导览",
      "category": "orientation",
      "dag_level": 0,
      "depends_on": null,
      "capability_ids": [],
      "study_minutes": {"tier": "orientation", "min": 15, "max": 30},
      "lesson": {"prerequisites": [], "problem": {}, "outcomes": [], "concepts": [], "examples": [], "capstone_bridge": {}, "summary": []},
      "quiz": []
    },
    {
      "id": "prep01",
      "title": "Prep 01：路径值与文件系统效果",
      "category": "library",
      "dag_level": 1,
      "depends_on": "lab00",
      "capability_ids": ["path-value-boundary"],
      "study_minutes": {"tier": "standard", "min": 30, "max": 45},
      "lesson": {"prerequisites": [], "problem": {}, "outcomes": [], "concepts": [], "examples": [], "capstone_bridge": {}, "summary": []},
      "quiz": []
    }
  ],
  "labs": []
}
```

## Stable identity and evidence

Course, source, preparatory-unit, Lab, prerequisite, outcome, concept, example, quiz, choice, and coding-question IDs are stable. Preparatory IDs are `lab00`, then contiguous `prep01` through `prepNN`. Formal Lab IDs remain contiguous `lab01` through `labNN`. Dependencies form one chain across prep units and then formal Labs.

Every official source is a primary HTTPS source with a title and applicable version or revision. Concepts cite registry IDs through `source_claims`, never an unregistered free-form URL. Each claim is marked `documented` for a public contract or `implementation` for a version-pinned implementation observation. Do not turn an implementation detail into a promised API.

`target.import_roots` lists the top-level Python packages whose use is controlled by the mechanism cycle. Third-party targets require pinned or bounded PEP 508 dependencies. Standard-library courses may leave dependencies empty.

## Assessed readiness and duration

New Skill-authored specifications use `course.audience.level: assessed`. The profile contains `assessment: evidence-dialogue`, the selected `route_id`, the plan's 12-character `readiness_summary`, and a nonempty `capabilities` array. Validation also receives the complete readiness plan and rejects any mismatch before scaffolding can write.

Each capability contains exactly `"id"`, `"kind"`, `"subject"`, `"title"`, `"status"`, `"decision"`, `"basis"`, `"source_ids"`, `"first_used_in"`, `"preparatory_unit_id"`, and `"preparatory_concept_ids"`:

- `kind` is `python`, `library`, or `domain`;
- `status` is the completed decision `known` or `missing`;
- `decision` is `assume` or `preparatory`;
- `basis` records the privacy-safe evidence class, never the raw answer or code.

Capability IDs are stable and unique. A `known` capability uses `assume`, a null prep ID, and no prep concepts. A `missing` capability uses `preparatory`, names exactly the prep unit allocated by the plan, and maps to at least one concept inside it. Source IDs resolve to the official registry, `first_used_in` resolves to a formal Lab, and each mapped concept cites at least one capability source.

`lab00` is always the 15-30 minute environment and learning-loop orientation. Missing capabilities are grouped into the smallest necessary `prepNN` units by DAG level and then `python -> library -> domain`. Each prep follows **existing cognitive anchor -> define the term -> why the current route needs it now -> complete concrete example and value flow -> common misconception or applicability boundary -> recovery and check**. It contains lessons, runnable teaching examples, traces, diagnostics, and quizzes, but no coding questions, points, submissions, reference projection, or hidden tests.

There is no hard prep-count ceiling. Cover only capabilities actually used by the selected route. Multiple dependency layers become multiple ordered prep units in the same course rather than forcing an artificial stop or separate prerequisite course.

Every assessed unit owns an exact `study_minutes` object:

- `lab00`: `{"tier": "orientation", "min": 15, "max": 30}`;
- ordinary prep or formal Lab: `{"tier": "standard", "min": 30, "max": 45}`;
- derivation- or lifecycle-heavy prep or Lab: `{"tier": "extended", "min": 45, "max": 60, "reason": "..."}`.

In learner-facing estimates these are 15-30, 30-45, and 45-60 minutes respectively.

`min` and `max` are JSON integers, not booleans or numeric strings. `reason` is nonempty where required, and the closed shapes above allow no extra fields.

Schema-v2 `basic-python` and `assessed/learner-self-report` specifications remain readable compatibility inputs with their original single-`foundation` behavior. They are not new authoring defaults.

## Structured `lesson`

Every `lab00`, `prepNN`, and formal Lab uses the same `lesson` object:

```json
{
  "prerequisites": [
    {
      "id": "lab01.p-functions",
      "title": "函数与返回值",
      "why": "本练习通过一个函数边界暴露可观察行为。",
      "refresh": "函数接收明确的输入，并返回一个明确的结果。"
    }
  ],
  "problem": {
    "context": "文件整理器需要安全地表示根目录和子文件。",
    "naive_approach": "直接用斜杠拼接字符串。",
    "failure": "分隔符、路径类型和文件系统效果混在了一起。"
  },
  "outcomes": [
    {"id": "lab01.o-trace", "text": "追踪输入、操作和输出的所有权。"},
    {"id": "lab01.o-diagnose", "text": "解释并修复一个错误的路径边界。"}
  ],
  "concepts": [
    {
      "id": "lab01.c-path-model",
      "name": "词法路径组合",
      "definition": "路径对象描述一个路径，但组合路径本身不执行文件系统 I/O。",
      "purpose": "它把路径表示与文件系统效果分开。",
      "mechanism": ["接收根路径和子名称。", "创建一个新的路径值。", "返回新值而不访问磁盘。"],
      "mental_model": "先把路径看成一张地址配方，而不是已经创建的文件。",
      "design_reasons": ["值对象让效果边界保持显式。"],
      "benefits": ["无需创建文件就能测试组合行为。"],
      "tradeoffs": ["真正读写文件时仍需要后续的显式 I/O。"],
      "invariants": ["仅组合路径不会写入文件系统。"],
      "boundaries": ["不同平台的路径规范化结果可能不同。"],
      "pitfalls": ["不要从组合后的路径推断文件一定存在。"],
      "source_claims": [
        {"source_id": "python-pathlib", "claim": "Path 提供词法路径组合操作。", "status": "documented"}
      ],
      "operational_contract": {
        "kind": "api",
        "forms": ["PurePath(root) / child"],
        "inputs": [
          {
            "name": "root_and_child",
            "meaning": "要组合的根路径值与一个子名称。",
            "form": "PurePath 与 str",
            "example": "PurePath('root'), 'a.txt'",
            "constraints": ["子名称必须是本路线允许的相对路径片段。"]
          }
        ],
        "outputs": [
          {
            "name": "destination",
            "meaning": "组合后得到的新路径值。",
            "form": "PurePath",
            "example": "PurePath('root/a.txt')"
          }
        ],
        "effects": ["返回新路径值，不创建文件，也不修改输入。"],
        "failure_modes": [
          {
            "condition": "调用者把路径组合误当成文件创建。",
            "observable": "磁盘上没有出现对应文件。",
            "recovery": "在后续步骤显式调用文件系统写入 API。"
          }
        ]
      }
    }
  ],
  "examples": [
    {
      "id": "lab01.e-run",
      "title": "组合一个子路径",
      "kind": "runnable",
      "path": "examples/01_compose.py",
      "code": "from pathlib import PurePath\nprint(PurePath('root') / 'a.txt')\n",
      "command": "python examples/01_compose.py",
      "expected_output": "root/a.txt",
      "explanation": "这个完整示例可以在 CPU/离线环境直接运行。",
      "concept_ids": ["lab01.c-path-model"],
      "outcome_ids": ["lab01.o-trace"],
      "trace": [
        {
          "id": "lab01.t-root",
          "concept_ids": ["lab01.c-path-model"],
          "input_state": "root = PurePath('root')，child = 'a.txt'",
          "operation": "读取两个调用输入，但不访问文件系统。",
          "output_state": "root.parts == ('root',)，child 仍是 str。",
          "explanation": "这一步确认输入形式和调用者仍拥有原值。"
        },
        {
          "id": "lab01.t-compose",
          "concept_ids": ["lab01.c-path-model"],
          "input_state": "root = PurePath('root')，child = 'a.txt'",
          "operation": "计算 root / child。",
          "output_state": "destination = PurePath('root/a.txt')，磁盘未发生变化。",
          "explanation": "组合产生一个新路径值；它没有创建文件。"
        }
      ]
    },
    {
      "id": "lab01.e-bug",
      "title": "把路径表示与 I/O 分开",
      "kind": "diagnostic",
      "wrong_code": "open('root/' + name, 'w')\n",
      "symptom": "一个本应只返回路径的辅助函数却创建了文件。",
      "cause": "路径表示和文件系统效果被藏在同一个操作里。",
      "fix_code": "from pathlib import PurePath\ndef target(name):\n    return PurePath('root') / name\n",
      "explanation": "这个例子沿着 wrong -> symptom -> cause -> fix 解释效果边界。",
      "concept_ids": ["lab01.c-path-model"],
      "outcome_ids": ["lab01.o-diagnose"]
    }
  ],
  "capstone_bridge": {
    "input": "一个已验证的根路径和子名称。",
    "output": "一个词法目标路径值。",
    "increment": "为整理器加入安全的目标路径表示。",
    "next": "下一课用官方 Path API 替换手写的表示边界。"
  },
  "summary": ["路径表示不同于文件系统效果。", "下一课会考查官方 bridge。"]
}
```

Write each new lesson from the assessed readiness evidence and its unit-specific `study_minutes`, not from a universal beginner label or duration. Each concept still defines the term, purpose, mechanism, mental model, design reasons, benefits, tradeoffs, invariants, boundaries, pitfalls, and source claims.

Every graded lesson expands one new knowledge mainline through the existing fields in this order: **project problem**, **plain-language predictive model**, **precise inputs, outputs, effects, and failures**, **same concrete value through the complete flow**, **valid case and boundary case**, **diagnosis and recovery**, then **quiz, coding question, and capstone increment**. Those practice surfaces map to the same concept and outcome. Render them as connected natural Simplified Chinese, not as an author-field inventory.

In assessed mode every concept also has a closed `operational_contract` with exactly:

- `kind`: `api`, `mechanism`, `formula`, `lifecycle`, or `data-model`;
- nonempty `forms` and `effects` string arrays;
- nonempty `inputs`, each with `name`, `meaning`, `form`, `example`, and nonempty `constraints`;
- nonempty `outputs`, each with `name`, `meaning`, `form`, and `example`;
- nonempty `failure_modes`, each with `condition`, `observable`, and `recovery`.

Every assessed runnable example adds a `trace` of at least two steps. Each step has exactly a stable unique `id`, nonempty mapped `concept_ids`, `input_state`, `operation`, `output_state`, and `explanation`. Step concept IDs stay within both the lesson and the runnable example's concept mappings. Carry the same concrete value or state across the steps and match the convention graded by the tests.

Every lesson has at least two examples. One is a complete runnable file with an exact command and expected output. One is a diagnostic with wrong code, visible symptom, root cause, and fixed code: wrong -> symptom -> cause -> fix. Accelerator-only surfaces use metadata, configuration, source traces, or preflight examples; mandatory examples and grading stay CPU/offline runnable.

For a runnable example whose lesson-relative file is `{path}`, the command is exactly `python {path}`. Shell wrappers, `python -m`, chained commands, alternate interpreters, and extra flags are outside this deterministic example contract.

The rule against prerequisite leakage is strict: a prerequisite may refresh only material introduced in an earlier course unit. New syntax, framework concepts, and mathematics belong in the current prep or Lab's open definitions and runnable trace. Every exact formula graded by public or hidden tests needs a worked numeric derivation visible before the exercise.

Assessed coverage is exact across authored surfaces:

- every orientation/prep concept maps to a runnable trace, quiz, and diagnosis;
- every graded-Lab concept maps to a runnable trace, quiz, coding question, and diagnosis;
- diagnosis coverage may come from a diagnostic example or diagnostic quiz;
- every outcome maps to an example and to an assessment: a quiz in a prep unit, or a quiz/coding question in a graded Lab.

Examples, quiz items, and coding questions carry forward `concept_ids` and `outcome_ids`. Authors order those activities intentionally. The compiler derives each concept's first-practice link from that authored order; do not serialize reverse `practice_links` into the specification.

The cumulative capstone must carry meaningful values through the promised route. A stage-name-only tuple, callback log, or fake plumbing trace is not integration. Capstone tests perturb identities, masks, values, configuration branches, and ordering so bypassing an earlier responsibility fails observably.

## Knowledge checks

Each preparatory unit and formal Lab has both an execution-trace and a diagnostic question. A question has:

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

The next bridge's `official_symbols` is responsibility-complete: its set exactly equals the immediately previous reimplementation's `target_symbols`. Every declared `required_imports` root appears directly in both starter and reference bridge files. Every `reimplementation` question points to the declared `learner_file`; that file and its reachable declared helpers reject target roots, prior-Lab helpers, prior mini modules, aliased imports, and literal `importlib.import_module(...)` or `__import__(...)` delegation.

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
├── preparatory_units/
│   └── {lab00,prepNN}/
│       ├── lesson.json
│       ├── quiz.json
│       └── examples/*.py
└── labs/labNN/
    ├── lab.json
    ├── lesson.json
    ├── examples/*.py
    ├── starter/**
    ├── reference/**
    └── tests/{public,hidden}/**
```

There is no editable `source/authoring-spec.json`. The compiler independently validates direct split-source edits, renders a complete Markdown fallback, preserves the reconstructable `lesson_outline`, and emits `compiled/authoring-spec.json` as a private compiler-generated parity snapshot. Scaffolding then checks that snapshot is structurally equal to the validated input specification.

A schema-v3 curriculum ID is exactly `<course-id>-v3-<readiness_summary>`. A different readiness summary is intentionally incompatible and resets learner progress. Schema-v2 IDs keep their original `-v2` form. Do not automatically bump progress-state `version`, artifact-index `schema_version`, `engine_version`, or `layout_version`; those are separate runtime contracts.

## Adaptive size

- `small`: 3-5 graded Labs.
- `medium`: 6-8 graded Labs.
- `large`: select one coherent track first, then 6-10 graded Labs.

Count public capabilities and product surfaces before choosing. Every selected route must fit one environment and one cumulative capstone. If a broad target still has multiple plausible tracks, stop before creating files and ask for the one material choice.
