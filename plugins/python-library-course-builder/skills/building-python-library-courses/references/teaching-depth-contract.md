# Teaching depth contract

Use this positive recipe after the private readiness sequence and before route, specification, or lesson design. The goal is natural teaching material in the selected `zh-CN` or `en` locale whose depth is visible in concrete values, contracts, traces, and aligned practice. Readiness chooses the route on the author side; it is never a subject of the generated lecture.

Use the [complete teaching example index](complete-teaching-example.md) to open exactly one locale-specific example before writing learner-facing prose: [Simplified Chinese](complete-teaching-example.zh-CN.md) for `zh-CN` or [English](complete-teaching-example.en.md) for `en`. Each demonstrates the same recipe as connected teaching rather than as a field inventory.

## Contents

- [Turn readiness evidence into ordered prep](#turn-readiness-evidence-into-ordered-prep)
- [Keep readiness outside the tutorial](#keep-readiness-outside-the-tutorial)
- [Teach every evidenced gap completely](#teach-every-evidenced-gap-completely)
- [Expand every graded chapter](#expand-every-graded-chapter)
- [Use one chapter progression](#use-one-chapter-progression)
- [Close the operational contract](#close-the-operational-contract)
- [Carry one value through the trace](#carry-one-value-through-the-trace)
- [Prove every declared boundary end to end](#prove-every-declared-boundary-end-to-end)
- [Write natural learner-facing prose](#write-natural-learner-facing-prose)
- [Adapt the recipe to the concept kind](#adapt-the-recipe-to-the-concept-kind)
- [Align every activity](#align-every-activity)
- [Choose time from the work](#choose-time-from-the-work)
- [Review semantically](#review-semantically)

## Turn readiness evidence into ordered prep

Keep `lab00` as a 15-30 minute environment and learning-loop orientation. Build any additional preparatory teaching from the completed readiness plan:

1. Reuse sufficient code evidence and conversation evidence tied to a matching, correctly answered route diagnostic; do not ask again or reteach that capability. Never promote free-form self-description to mastery evidence.
2. Group missing capabilities by prerequisite-DAG level and then `python -> library -> domain`.
3. Create the minimum `prep01 -> prep02 -> ...` sequence needed by the selected route. Do not impose a hard count ceiling.

Treat unseen material as new teaching, not review. Map every `preparatory` capability to concepts in its assigned prep unit and to supporting official sources. A capability marked `assume` needs no prep concept. Never place raw learner answers or code evidence in the course repository.

## Keep readiness outside the tutorial

Use the readiness plan only to decide which ordinary course chapters exist. Never copy its labels or rationale into `tutorial`, the structured lesson sidecar, quiz feedback, README, sidebar text, manifests, or learner APIs. Learner-facing material must not state or imply a level, profile, capability status, evidence result, diagnostic answer, preparation decision, or phrases such as “you already know” and “your gap.”

A prep chapter can begin from a curricular fact established by an earlier chapter, such as “the previous chapter returned a dictionary.” It cannot claim that a private assessment proved the learner already understands dictionaries. Teach the selected foundation fully and naturally; do not tell the learner why the authoring system selected it.

## Teach every evidenced gap completely

Keep different DAG layers and `python`, `library`, and `domain` categories clear in the private curriculum mapping. Give every selected preparatory subject one complete explanation with this reasoning progression:

1. **curricular anchor** — begin with a behavior, value, or code pattern established in the course or introduced concretely in this chapter, without making a claim about the learner;
2. **define the term** — introduce one precise term in plain language and distinguish it from the nearby idea most likely to be confused with it;
3. **why the current route needs it now** — name the next Lab operation or capstone decision that would otherwise be unpredictable;
4. **complete concrete example and value flow** — carry one real value from its starting form through each relevant intermediate form to the observable result;
5. **common misconception or applicability boundary** — show one plausible wrong prediction or out-of-scope input and the symptom it produces;
6. **recovery and check** — repair that exact case, run or inspect it again, and ask the learner to predict or verify the recovered result.

Do not collapse several foundations into one generic prerequisite paragraph. If two private capabilities share a concept, keep both mappings in the authoring sidecar while teaching the shared value flow once in natural prose.

## Expand every graded chapter

Give each graded chapter one new knowledge mainline and expand it in this order:

1. **project problem** — identify the capstone behavior this chapter must add;
2. **plain-language predictive model** — state the ordinary-language idea that lets the learner predict what the code will do;
3. **precise inputs, outputs, effects, and failures** — state the closed behavior before discussing implementation detail;
4. **same concrete value through the complete flow** — reuse one input across every named transition and show each intermediate form that affects the result;
5. **valid case and boundary case** — compare a normal input with a nearby input that changes validity or interpretation;
6. **diagnosis and recovery** — connect the boundary to its symptom and cause, apply the recovery, then show the corrected observable;
7. **quiz, coding question, and capstone increment** — make all three practice surfaces apply the same concept and outcome introduced by the value flow.

An official bridge may reinforce the preceding mechanism, but it does not replace this chapter's new mainline or justify another unrelated topic.

## Use one chapter progression

Make this conceptual progression discoverable in every orientation, prep, and graded Lab, omitting the coding step from all preparatory units:

1. **concrete capstone problem** — name the observable problem this increment solves;
2. **plain-language understanding** — give the learner one predictive idea in ordinary language;
3. **exact operational contract** — close the forms, inputs, outputs, effects, and failures;
4. **complete real-value execution trace** — carry one input or state through the mechanism;
5. **boundary and error reasoning** — connect an invalid case to its symptom, cause, and recovery;
6. **runnable and diagnostic examples** — make both paths executable or directly inspectable;
7. **knowledge check** — ask for a trace prediction and a diagnosis;
8. **coding or capstone increment** — make the learner apply the same concept to the cumulative product.

Keep one new knowledge mainline per graded Lab. Lab 02+ may open with the previous mechanism's official bridge, but the bridge is reinforcement and replacement, not permission to add a second unrelated mainline. These items are authoring coverage, not a mandatory series of identical headings. Let the subject determine section boundaries and transitions.

## Close the operational contract

Give every assessed concept one `operational_contract`. Fill each slot with concrete learner-facing information:

- `kind`: one of `api`, `mechanism`, `formula`, `lifecycle`, or `data-model`;
- `forms`: visible call, notation, state transition, or data forms the learner will encounter;
- `inputs`: names, meanings, forms/types, real examples, and constraints;
- `outputs`: names, meanings, forms/types, and real examples;
- `effects`: observable mutation, I/O, state, ownership, or an explicit no-effect guarantee;
- `failure_modes`: at least one `condition`, resulting `observable`, and usable `recovery`.

Close the contract around the behavior that examples and tests actually exercise. Do not promise upstream internals as public behavior. Cite the primary source for public claims and label version-pinned implementation observations separately.

Use the kind to choose the visible form:

| Kind | Make visible |
|---|---|
| `api` | exact call form, accepted values, return/raise behavior, side effects, and version boundary |
| `mechanism` | ordered transformation steps, invariants, intermediate representation, and delegation boundary |
| `formula` | notation, symbol meanings, units/shapes, convention, intermediate arithmetic, and invalid domain |
| `lifecycle` | owner, initial state, event, transition, final state, cleanup, and illegal transition |
| `data-model` | valid shapes/variants, identity and ownership, conversions, preserved fields, and rejected forms |

## Carry one value through the trace

Carry the **same concrete value or state** through **at least two named transitions**. Each structured trace step supplies a stable ID, mapped concept IDs, `input_state`, `operation`, `output_state`, and `explanation`.

Show intermediate **shapes, types, state, or ownership** wherever they determine behavior. Match the convention used by the tests: dimension order, correction term, event order, error class, ownership rule, and version must not drift between lesson, trace, code, and tests. Never substitute generic “execute one operation” prose for a value flow.

A compact complete trace can look like this:

```text
parse-input
  input_state: text = '{"ready": true}' (str, owned by caller)
  operation: json.loads(text)
  output_state: value = {'ready': True} (new dict)
  explanation: JSON true becomes Python True; text is unchanged.

read-field
  input_state: value = {'ready': True}
  operation: value['ready']
  output_state: ready = True (bool)
  explanation: The key lookup exposes the exact value used by the capstone branch.
```

The runnable example contains this value flow and exact expected output. The diagnostic example perturbs one constraint and follows wrong code -> symptom -> cause -> fix.

## Prove every declared boundary end to end

For each declared `failure_modes` entry and each independently stated boundary, build one **boundary witness** before delivery. Reuse one witness when both declarations describe the same condition; leave neither declaration without a witness.

1. Choose a representative invalid input or state that satisfies the stated condition.
2. For that counterexample, execute the actual example or reference path.
3. Record the exact observed output or exception, then compare it with the declared observable.
4. Then apply the declared recovery, re-execute the corrected path, and record the recovered observable to prove that the recovery works.
5. Keep that condition, observable, and recovery identical across the prose contract, runnable or diagnostic code, expected output, diagnostic quiz and, for graded concepts, the coding prompt plus public and hidden tests.

Reject delivery when a declared failure or boundary is merely listed but its counterexample and recovery are not implemented and exercised on every applicable activity and test surface.

## Write natural learner-facing prose

When a signpost helps, use a natural equivalent of these phrases in the selected locale; do not force every chapter to repeat them as headings:

| Meaning | `zh-CN` | `en` |
|---|---|---|
| predictive mental model | `先这样理解` | `Start with this mental model` |
| operational contract | `输入和输出是什么` | `What are the inputs and outputs?` |
| concrete trace | `拿一个具体输入走一遍` | `Walk one concrete input through the flow` |

Write the connected explanation naturally in the selected language. Define every professional term at first use in a clear sentence. Immediately connect it to the current task. Add a natural transition into a concrete value, then explain what changes and why before naming the next structure. Never turn `definition -> purpose -> mechanism -> boundaries -> pitfalls` into a learner-facing author-field inventory; those authoring fields must read as one connected explanation, not stacked labels.

Define a term at first use, then immediately connect it to the current capstone problem. Use short natural transitions appropriate to the selected locale. Alternate explanation with concrete values instead of presenting a schema-field dump. Prefer connected sentences over a stiff glossary, and explain jargon before using it in a prediction or exercise.

Make `tutorial` Markdown the primary learner-facing chapter and keep the structured lesson as its validation sidecar. The tutorial may interleave implementation detail, design tradeoffs, and source notes where they help the explanation. Do not expose internal mapping IDs, author-facing enum labels, readiness data, or the sidecar's field structure as learner prose.

Use enough detail to make each transition predictable: show intermediate forms, explain why the operation changes them, define nearby terms before relying on them, and connect symptoms to causes. Do not set a fixed word count. Expand because the mechanism needs explanation, not because a template needs another paragraph.

## Adapt the recipe to the concept kind

### Numeric formula

Name every symbol and its unit or shape. Substitute one full set of numbers, show each intermediate result, state the tested convention, then connect the result to code. Include a boundary that changes validity or interpretation.

### Data or shape transformation

Show the complete before value, the operation, and the complete after value. Trace dimension order, type conversion, preserved identity, copying/aliasing, and ownership when relevant. Include one superficially plausible shape or variant that fails and explain why.

### State or lifecycle flow

Name the state owner and initial state. Apply a real event, show the intermediate and final states plus visible output, then show cleanup or recovery. Include one illegal transition and its observable behavior.

### Public API boundary

Show the exact pinned call, concrete accepted input, returned value or raised error, effects, and version/source boundary. When a teaching-equivalent precedes it, compare declared observables through the official API rather than importing the earlier mini implementation.

## Align every activity

Map authored activities forward from concepts and outcomes:

- every assessed concept reaches a runnable trace, quiz, and diagnosis;
- every graded-Lab concept also reaches a coding question;
- every outcome reaches an example and at least one quiz or coding assessment;
- each question and example names the concept/outcome IDs it actually exercises.

Order activities intentionally. The compiler derives each concept's **first practice link** from authored activity order: preparatory units point to the first mapped knowledge check, and graded Labs point to the first mapped coding question. Authors maintain the forward mappings only; do not add reverse practice-link fields to the specification.

## Choose time from the work

- `lab00` uses the `orientation` tier, **15-30 minutes**.
- An ordinary prep or graded Lab uses the `standard` tier, **30-45 minutes**.
- A derivation- or lifecycle-heavy prep or Lab may use the `extended` tier, **45-60 minutes**, with a specific reason naming that work.

Do not pad a Lab to fit a tier. Narrow the mainline when the planned explanation, trace, diagnosis, and coding increment cannot fit coherently.

## Review semantically

Review the learner-visible contract, concrete trace, mapped activities, source/version discipline, and natural selected-language prose as connected teaching. A prose **word count** is not the primary quality gate. Reject a chapter that is long but generic, structurally complete but internally inconsistent, mixed-locale, or silently translated through a fallback.
