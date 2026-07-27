# Authoring guidance v4

This is prompt guidance for the parent Agent and chapter Writer. It is not a machine-scored rubric.

## Parent Agent

- Select one cumulative route and one knowledge mainline per chapter.
- Lock official facts, public interfaces, task IDs, selectors, dependencies, and owned paths before Writers start.
- Give each chapter one core question, one concrete walkthrough, one recoverable boundary case, one selected design, and one credible alternative.
- Keep Depth Briefs small and chapter-local. Do not send the full course specification, other chapters' prose, raw readiness evidence, a long example, or semantic mapping tables.
- Make capstone chapters compose earlier public interfaces, not private teaching implementations.

## Chapter Writer

- Write connected textbook prose with subject-driven headings.
- Define terms when they first become necessary.
- Carry the same concrete value/state through explanation, quiz, code, and tests.
- Make component responsibility, dependency direction, and caller/implementer boundary visible.
- Explain why the selected design fits and when the alternative would become preferable.
- Connect the boundary's symptom to its cause, recovery, and corrected observable.
- Keep quiz and coding work on the same mechanism.
- Perform the silent single-call self-review in [chapter-writer-contract.md](chapter-writer-contract.md), revise internally, and return only final files.

## Things not to optimize

Do not optimize for:

- chapter word count;
- a fixed heading inventory;
- keyword presence;
- number of concepts;
- coverage percentages;
- depth bands or scores;
- concept/outcome/trace mappings; or
- making every chapter look structurally identical.

`lab00` may be short and operational. A difficult mechanism may be long. The relevant question is whether the learner can predict and implement the chosen mechanism.

## Mechanical consistency

The generated package must still be runnable:

- task IDs, files, symbols, and selectors match the parent locks;
- starter and solution parse;
- public and hidden tests collect;
- quiz answers reference real choice IDs;
- owned paths are safe and conflict-free; and
- learner output contains no answers, solutions, or hidden material.

These are mechanical acceptance conditions, not proxies for teaching quality.
