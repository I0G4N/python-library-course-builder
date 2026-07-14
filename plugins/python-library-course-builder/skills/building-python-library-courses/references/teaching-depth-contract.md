# Teaching depth contract

Use this positive recipe after the readiness sequence and before route, specification, or lesson design. The goal is natural Simplified-Chinese teaching material whose depth is visible in concrete values, contracts, traces, and aligned practice.

## Contents

- [Turn readiness evidence into Lab 00](#turn-readiness-evidence-into-lab-00)
- [Use one chapter sequence](#use-one-chapter-sequence)
- [Close the operational contract](#close-the-operational-contract)
- [Carry one value through the trace](#carry-one-value-through-the-trace)
- [Write natural learner-facing Chinese](#write-natural-learner-facing-chinese)
- [Adapt the recipe to the concept kind](#adapt-the-recipe-to-the-concept-kind)
- [Align every activity](#align-every-activity)
- [Choose time from the work](#choose-time-from-the-work)
- [Review semantically](#review-semantically)

## Turn readiness evidence into Lab 00

Build a **two-layer Lab 00** from the assessed prerequisite profile:

1. Fill only evidenced **general-Python gaps** needed by this route. Use the learner's supplied code, answers, or examples as evidence; do not dump every Python basic.
2. Teach the **route-specific library and domain foundations** needed before Lab 01, such as a data model, shape convention, unit, or lifecycle vocabulary.

Treat unseen new material as new teaching, not as review. Map every `foundation` capability to the Lab 00 concepts that teach it and to the official sources that support it. A capability marked `assume` needs no foundation concept. If several prerequisite layers cannot form one focused Lab 00, stop and offer a prerequisite course or narrower route.

## Use one chapter sequence

Use this sequence in order for Lab 00 and every graded Lab, omitting only the coding step from Lab 00:

1. **concrete capstone problem** — name the observable problem this increment solves;
2. **plain-language understanding** — give the learner one predictive idea in ordinary language;
3. **exact operational contract** — close the forms, inputs, outputs, effects, and failures;
4. **complete real-value execution trace** — carry one input or state through the mechanism;
5. **boundary and error reasoning** — connect an invalid case to its symptom, cause, and recovery;
6. **runnable and diagnostic examples** — make both paths executable or directly inspectable;
7. **knowledge check** — ask for a trace prediction and a diagnosis;
8. **coding or capstone increment** — make the learner apply the same concept to the cumulative product.

Keep one new knowledge mainline per graded Lab. Lab 02+ may open with the previous mechanism's official bridge, but the bridge is reinforcement and replacement, not permission to add a second unrelated mainline.

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

## Write natural learner-facing Chinese

Render the open learning path with these learner-safe labels:

- `先这样理解`
- `输入和输出是什么`
- `拿一个具体输入走一遍`

Define a term at first use, then immediately connect it to the current capstone problem. Use short transitions such as “先看输入”, “现在走一步”, and “这在这里重要，因为…”. Alternate explanation with concrete values instead of presenting a schema-field dump. Prefer connected sentences over a stiff glossary, and explain jargon before using it in a prediction or exercise.

Keep implementation details, design tradeoffs, and source notes available after the open core. Do not expose internal mapping IDs or author-facing enum labels as learner prose.

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

Order activities intentionally. The compiler derives each concept's **first practice link** from authored activity order: Lab 00 points to the first mapped knowledge check, and graded Labs point to the first mapped coding question. Authors maintain the forward mappings only; do not add reverse practice-link fields to the specification.

## Choose time from the work

- Lab 00 uses the `foundation` tier, **45-60 minutes**, with a specific reason tied to the assessed gaps it fills.
- An ordinary graded Lab uses the `standard` tier, **30-45 minutes**.
- A genuinely combined, derivation-heavy, or lifecycle-heavy Lab may use the `extended` tier, **45-60 minutes**, with a specific reason naming that work.

Do not pad a Lab to fit a tier. Narrow the mainline when the planned explanation, trace, diagnosis, and coding increment cannot fit coherently.

## Review semantically

Review the learner-visible contract, concrete trace, mapped activities, source/version discipline, and natural Chinese as connected teaching. A prose **word count** is not the primary quality gate. Reject a chapter that is long but generic, or structurally complete but internally inconsistent.
