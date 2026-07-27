# Teaching depth contract v4

Course Builder v4 obtains chapter depth from high-quality parent context and a single Writer's in-call revision. It does not use a semantic output schema, word count, depth score, keyword gate, Reviewer, or replacement loop.

## One core question and one mechanism

Each chapter has one question that the learner should be able to answer at the end. Narrow the chapter until one concrete walkthrough can connect:

- the mechanism's definition and purpose;
- where it lives in the cumulative project;
- who calls it and what the caller can observe;
- the value or control flow through the implementation;
- the chosen design and one genuinely viable alternative;
- the main benefit, cost, and invariant;
- one boundary input or state, its symptom and cause, and a usable recovery; and
- the quiz and, for graded chapters, the coding task.

Do not add a second mainline to make a chapter look deeper. A chapter is deep when the learner can predict the first mechanism, not when it lists more concepts.

The parent supplies 3–6 chapter-relevant `required_facts` from official sources. This is prompt guidance only; no generated schema or validator counts them.

## Use a concrete walkthrough

The parent supplies a concrete value or state, not a placeholder such as “some input.” The Writer carries that same case through the explanation, quiz, starter API, solution behavior, and tests.

Show each transition that changes an observable result. Name types, shapes, ownership, state, or effects when they matter. Explain why the transition occurs before moving on.

## Explain the interface and design naturally

Except in `lab00`, prose should make these facts discoverable without using fixed headings:

- the component's responsibility and upstream/downstream dependencies;
- the caller/implementer boundary: accepted input, returned result, effects, and failure behavior;
- the selected design;
- one credible alternative that could actually work;
- why the selected design fits this route;
- benefits and tradeoffs, including one important invariant or cost; and
- the concrete change that would justify revisiting the alternative.

These are Writer instructions, not JSON fields. They never become a checklist that a script searches for in Markdown.

## Make the boundary recoverable

Use one representative failing input or state. Connect:

```text
input/state -> visible symptom -> cause -> recovery -> corrected observable
```

The quiz and tests should exercise the same behavior boundary. The mechanical validator checks only that files, selectors, symbols, and answer references resolve; the Writer's silent self-review is responsible for explanatory quality.

## Adapt depth by chapter kind

### `lab00`

Teach environment setup, how the course is organized, and the complete loop:

```text
read -> answer quiz -> edit -> save -> public test -> hidden submit -> progress
```

Do not manufacture a design comparison or architecture section.

### `prepNN`

Teach one missing prerequisite mechanism as ordinary course content. Give it enough detail that the learner can predict the next Lab's behavior. Do not mention diagnostics, levels, gaps, readiness status, or why the system selected the chapter.

### Ordinary `labNN`

Center the chapter on one implementable mechanism and one runnable increment. Explain its interface, flow, selected design, credible alternative, boundary/recovery, and engineering tradeoffs through the same case.

### Integration or capstone

Reuse earlier public interfaces rather than earlier chapters' private implementations. Trace one end-to-end case across components. Emphasize dependency direction, composition, failure propagation, ownership, and system-level tradeoffs.

## No automated prose judgment

The following are explicitly forbidden for v4:

- required Markdown heading names or order;
- minimum/maximum tutorial length;
- keyword or phrase presence checks;
- `lesson.json`, `lesson_outline`, concepts, outcomes, operational contracts, or traces;
- concept-to-quiz/code/example mappings;
- depth bands, semantic completeness scores, padding or repetition detection;
- whole-course review Agents; and
- replacement Writer loops.

If a learner later finds a chapter shallow, regenerate only that chapter with a concrete reason while preserving the route, task IDs, public interfaces, and all other chapters.
