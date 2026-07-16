# Course authoring rubric

Apply this rubric before scaffolding and again when reviewing the generated course. A course is not strong merely because its reference tests pass.

## Contents

- [Evidence and versioning](#1-evidence-and-versioning)
- [Route coherence](#2-route-coherence)
- [Lesson quality](#3-lesson-quality)
- [Exercise design](#4-exercise-design)
- [Test and grading quality](#5-test-and-grading-quality)
- [Learning interfaces](#6-learning-interfaces)
- [Handoff and maintainability](#7-handoff-and-maintainability)
- [Review decision](#review-decision)

## 1. Evidence and versioning

- The target version is explicit and compatible with the generated environment.
- Every taught public behavior is supported by a direct primary official source.
- Documentation guarantees and upstream implementation details are labeled differently.
- Deprecated, provisional, optional, and platform-specific APIs are identified.
- Third-party dependency constraints are reproducible; no unpinned tutorial assumption is presented as a guarantee.

Reject the route if a core learning outcome depends on unverifiable behavior.

## 2. Route coherence

- Lab 00 gets a new learner from setup to one passing smoke command and explains the learning loop in 15-30 minutes.
- The `assessed` profile records **evidence-based readiness** rather than a beginner/intermediate label. Reuse user-supplied evidence and ask only about selected-route capabilities that remain unknown.
- Readiness remains private authoring state. Generated tutorials, sidecars, quizzes, manifests, documentation, navigation, and APIs contain no diagnostic answers, evidence, level/profile labels, capability IDs/status/decisions, readiness summaries, or personalized “you already know/your gap” framing.
- Missing capabilities become ordered `prepNN` units by DAG layer and `python -> library -> domain`; known capabilities do not produce fictional prep.
- Treat missing or unseen **new material** as teaching, not **review**; readiness evidence, not the author's intuition, decides which label applies.
- In each prep, every selected foundation follows one complete path: **curricular anchor** -> **define the term** -> **why the current route needs it now** -> **complete concrete example and value flow** -> **common misconception or applicability boundary** -> **recovery and check**. Keep the evidence-to-unit mapping private.
- An ordinary prep or graded Lab uses 30-45 minutes. Only derivation- or lifecycle-heavy work uses 45-60 minutes with a specific reason.
- Each graded Lab has only the prerequisites it needs and depends on the previous Lab.
- Reject prerequisite leakage: do not label syntax, framework behavior, or mathematics as a refresh unless an earlier lesson actually taught it.
- Concepts are introduced before use and revisited through composition rather than repeated prose.
- Every graded Lab follows **one new knowledge mainline**. **Lab 02+** may also begin with the immediately prior mechanism's official bridge; that bridge does not justify a **second unrelated mainline**.
- Lab N handwrites a teaching-equivalent from lower-level primitives; the immediately next Lab starts with a graded official bridge that compares declared observables through the pinned API.
- The next bridge covers every declared target symbol and every responsibility graded by the previous reimplementation questions; bridge metadata, code, observables, and tests must agree.
- No downstream learner/reference/test code or capstone imports a prior mini implementation; it calls the official API when it needs an earlier capability.
- Every Lab leaves the cumulative capstone more capable in an observable way.
- The final Lab integrates the route instead of becoming a disconnected bonus exercise.
- Reject a stage-name-only capstone: it must transform deterministic payload fields from the accumulated route, and tests must fail if identity, masks, ordering, or a selected configuration branch is bypassed.
- Course depth matches the small, medium, or selected-track range; Lab count is not padded.

For a broad library, prefer one deep product track over a catalog of unrelated subpackages.

## 3. Lesson quality

Make this reasoning progression discoverable: concrete capstone problem -> plain-language understanding -> exact operational contract -> complete real-value execution trace -> boundary and error reasoning -> runnable and diagnostic examples -> knowledge check -> coding/capstone increment. Treat it as authoring coverage, not a mandatory sequence of identical headings. Let each subject determine its narrative and place implementation or source details where they clarify the mechanism.

For every graded chapter, make the deeper teaching route inspectable as: **project problem** -> **plain-language predictive model** -> **precise inputs, outputs, effects, and failures** -> **same concrete value through the complete flow** -> **valid case and boundary case** -> **diagnosis and recovery** -> **quiz, coding question, and capstone increment**. The final three practice surfaces exercise the same concept and outcome, and the chapter retains one new knowledge mainline.

Write `tutorial` as connected, textbook-style Markdown in the selected `zh-CN` or `en` locale. Define every professional term at first use, immediately connect it to the current task, transition into a concrete value, and explain why the value changes before introducing the next structure. Reject mixed-locale prose, silent fallback, a rigid author-field inventory, repeated boilerplate headings, or thin prose padded to meet a word count. Keep the structured `lesson` as a validation sidecar whose facts and mappings agree with the tutorial; do not make its schema the learner-facing presentation.

For every concept, check that the structured lesson answers:

- What is the object or operation, in precise plain language?
- Why does it exist, and what problem does it solve here?
- What actually happens step by step when the code runs, and what mental model makes that trace predictable?
- Why was this design chosen, what benefits does it create, and what tradeoffs does it introduce?
- What state, ownership, lifetime, error, performance invariant, and applicability boundary matters?
- Which pitfalls are likely, and how does the learner move through wrong -> symptom -> cause -> fix?
- Which primary source supports each public or implementation claim?

The **operational contract** is closed around the tested behavior: kind; visible forms; inputs with meanings, forms, concrete examples, and constraints; outputs with examples; effects; and failure modes that connect condition -> observable -> recovery. Choose `api`, `mechanism`, `formula`, `lifecycle`, or `data-model` deliberately.

The **complete real-value execution trace** carries the same value or state through at least two named transitions. It shows intermediate shape, type, state, or ownership where relevant and uses the exact convention graded by tests. Generic “execute one operation” prose is not a trace.

Before delivery, require a **boundary witness** for every declared failure and every independently stated boundary. Execute one representative counterexample, compare its observed result with the contract, apply the declared recovery, re-execute the corrected path, and record the recovered observable. Keep the condition, observable, and recovery consistent across the prose contract, runnable or diagnostic code, expected output, diagnostic quiz and, for graded concepts, coding prompt plus public and hidden tests. Reject a declaration that is only described but not implemented and exercised.

Every chapter has at least two examples: a complete CPU/offline runnable program with command and expected output, and a diagnostic with wrong code, symptom, cause, and fixed code. The runnable program is executed against the untouched starter projection before coding unlock, so it cannot import or call an incomplete learner TODO; use self-contained code or only fully pre-scaffolded helpers. Examples must be minimal and aligned with the pinned version. Use Python syntax highlighting and a true monospace font in both lecture code blocks and the editor. Let the primary tutorial explain the problem, terms, runnable flow, deeper principles, design tradeoffs, and diagnosis in a natural order. Keep a complete Markdown fallback. Keep prose readable at ordinary browser zoom; avoid oversized headings, crowded cards, duplicate panels, or a wide empty work area while coding is locked.

If an exercise grades an exact recurrence, estimator, loss, shape transformation, event-loop trace, or lifecycle, the open lesson includes a worked numeric derivation or complete worked execution trace before the TODO. The derivation names every symbol, shows intermediate values, and matches the tested convention rather than assuming domain background.

Every chapter has both an execution-trace and a diagnostic knowledge question. Each uses 3-4 stable choice IDs, feedback for every choice, `answer_id`, and concept/outcome mappings. Across the whole bank, use every answer position and keep each position at or below 40%.

## 4. Exercise design

- Every assessed concept reaches trace, quiz, and diagnosis; every graded-Lab concept also reaches coding. Every outcome reaches an example plus a quiz or coding assessment.
- Authored examples, quizzes, and coding questions map forward to the concepts/outcomes they exercise. The compiler derives the concept-ordered **first practice link** from authored activity order; authors do not maintain reverse mappings.
- Prompts specify observable behavior without revealing the implementation.
- Function and class interfaces are small enough to complete in one study session.
- Starter code has one intentional gap per declared interface and no accidental failure.
- Examples clarify edge semantics but do not encode every test case.
- Exercises require using the target capability meaningfully; they cannot be passed by returning constants or copying prompt data.
- An official bridge is the first coding question after Lab 01; the same Lab then handwrites the next teaching-equivalent.
- Mini implementations reject target imports and anti-delegation tests prevent a learner from wrapping the official function being explained.
- Points reflect relative effort and are derived into all score displays.

Prefer functions with explicit inputs and return values. Wrap filesystem, process, clock, randomness, or network boundaries so tests remain deterministic.

## 5. Test and grading quality

Public tests should provide fast local feedback and readable failure messages. Hidden tests should add boundaries, composition, mutation/aliasing, error behavior, or anti-hardcoding checks that are already implied by the prompt.

For every exercise, prove:

- starter imports successfully;
- its declared tests fail for the intended missing behavior;
- reference passes public tests;
- reference passes hidden tests;
- tests cannot read private artifacts or escape temporary workspaces;
- selectors identify the exercise precisely;
- rerunning tests produces the same result.
- public and hidden source contracts reject any import of a prior mini implementation;
- mandatory examples and tests are CPU/offline runnable, with GPU-only behavior limited to config/metadata/preflight validation.

Never accept a timeout, collection error, missing package, or syntax error as starter RED. Never weaken a valid test solely to make the reference GREEN.

## 6. Learning interfaces

- CLI and Web read the same learner manifest and report the same chapters, points, and status without exposing the author-side readiness profile or capability decisions.
- In v3 the chapter navigation gate initially exposes only Lab 00, unlocks prep units in order through knowledge mastery, then exposes Lab 01; schema v2 keeps its original behavior.
- The knowledge gate uses a generic, data-driven Web quiz and reveals no answer key. Prep has no coding surface; formal coding waits for the complete prep chain and current-Lab mastery.
- The coding verification gate completes a Lab only after every declared coding question passes verified submission; public success alone does not unlock the next Lab.
- `unlock`, `test`, `grade`, `submit`, `checkpoint`, and `score` each have a documented learner purpose.
- The Web lesson explains the current Lab beside a syntax-highlighted coding surface.
- Runner errors are structured and actionable; learner files remain intact after failed runs.
- Progress survives a normal restart and is isolated by curriculum ID.
- Initial and refreshed Web state fails closed; stale snapshots or late save/run responses cannot relock navigation or overwrite a newly selected Lab, and failed answer submissions remain retryable.
- Optional course-specific panels and commands appear only when declared.
- Before knowledge mastery unlocks coding, use a focused reading layout: the tutorial fills a comfortable text column and, on wide screens, a chapter guide provides heading navigation, terminology, and the knowledge check. Do not mount or call the code/file surface while it is locked. After mastery, return to the resizable lecture/code layout and keep the knowledge check reviewable.

## 7. Handoff and maintainability

- The root README gives prerequisites, setup, launch URLs, first action, local IDE workflow, browser workflow, tests, and Ctrl+C shutdown.
- `labs/README.md` points to `lab00` and explains which files learners should edit.
- Maintainer instructions explain canonical source compilation and drift checks.
- Structured split source reconstructs a byte-stable lesson outline and a compiler-generated parity snapshot equal to the validated schema-v3 input; schema-v2 parity remains compatible.
- Every expected unit is written by its own clean-context writer from a sanitized packet. Deterministic assembly proves one fragment per unit and preserves parent-owned IDs, sources, code, tests, module cycles, and bridges. A separate clean-context whole-course reviewer checks the assembled result; each failed unit is regenerated by a replacement writer.
- The output contains no absolute generator path, source-project symlink, unresolved template token, foreign brand, or fixed Lab/score assumption.
- The repository states that hidden tests are not secret if private artifacts are published.

## Review decision

Record findings by severity. A Critical or Important issue in evidence, grading correctness, path safety, private-artifact exposure, deterministic setup, or cumulative route blocks release. Fix generator-level causes before regenerating and rerunning the complete verification matrix.
