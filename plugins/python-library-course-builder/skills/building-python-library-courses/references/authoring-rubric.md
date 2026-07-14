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

- Lab 00 gets a new learner from setup to one passing smoke command.
- The `assessed` profile records **evidence-based readiness** rather than a beginner/intermediate label. Reuse user-supplied evidence and ask only about selected-route capabilities that remain unknown.
- A **two-layer Lab 00** fills only evidenced **general-Python gaps**, then teaches the **route-specific library and domain foundations** needed before Lab 01. Treat unseen **new material** as teaching, not **review**.
- Lab 00 uses 45-60 minutes with a gap-specific reason. An ordinary graded Lab uses 30-45 minutes. Only a genuinely combined, derivation-heavy, or lifecycle-heavy Lab uses 45-60 minutes with a specific reason.
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

Use one visible sequence: concrete capstone problem -> plain-language understanding -> exact operational contract -> complete real-value execution trace -> boundary and error reasoning -> runnable and diagnostic examples -> knowledge check -> coding/capstone increment. Render the open core with the learner-safe labels `先这样理解`, `输入和输出是什么`, and `拿一个具体输入走一遍` before deeper implementation and source details.

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

Every chapter has at least two examples: a complete CPU/offline runnable program with command and expected output, and a diagnostic with wrong code, symptom, cause, and fixed code. The runnable program is executed against the untouched starter projection before coding unlock, so it cannot import or call an incomplete learner TODO; use self-contained code or only fully pre-scaffolded helpers. Examples must be minimal and aligned with the pinned version. Use Python syntax highlighting and a true monospace font in both lecture code blocks and the editor. Render readiness-matched prerequisites, problem, outcomes, and runnable examples first; place deeper principles/design tradeoffs and diagnostics in accessible native disclosures. Keep a complete Markdown fallback. Keep prose readable at ordinary browser zoom; avoid oversized headings, crowded cards, and duplicate panels.

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

- CLI and Web read the same manifest and report the same prerequisites, points, and status.
- The chapter navigation gate initially exposes Lab 00 and the first graded Lab, keeps later Lab controls disabled, and unlocks each only after its declared dependency is completed.
- The knowledge gate uses a generic, data-driven Web quiz, reveals no answer key, and blocks coding until foundation and current-Lab mastery are recorded.
- The coding verification gate completes a Lab only after every declared coding question passes verified submission; public success alone does not unlock the next Lab.
- `unlock`, `test`, `grade`, `submit`, `checkpoint`, and `score` each have a documented learner purpose.
- The Web lesson explains the current Lab beside a syntax-highlighted coding surface.
- Runner errors are structured and actionable; learner files remain intact after failed runs.
- Progress survives a normal restart and is isolated by curriculum ID.
- Initial and refreshed Web state fails closed; stale snapshots or late save/run responses cannot relock navigation or overwrite a newly selected Lab, and failed answer submissions remain retryable.
- Optional course-specific panels and commands appear only when declared.

## 7. Handoff and maintainability

- The root README gives prerequisites, setup, launch URLs, first action, local IDE workflow, browser workflow, tests, and Ctrl+C shutdown.
- `labs/README.md` points to `lab00` and explains which files learners should edit.
- Maintainer instructions explain canonical source compilation and drift checks.
- Structured split source reconstructs a byte-stable lesson outline and a compiler-generated parity snapshot equal to the validated schema-v2 input.
- The output contains no absolute generator path, source-project symlink, unresolved template token, foreign brand, or fixed Lab/score assumption.
- The repository states that hidden tests are not secret if private artifacts are published.

## Review decision

Record findings by severity. A Critical or Important issue in evidence, grading correctness, path safety, private-artifact exposure, deterministic setup, or cumulative route blocks release. Fix generator-level causes before regenerating and rerunning the complete verification matrix.
