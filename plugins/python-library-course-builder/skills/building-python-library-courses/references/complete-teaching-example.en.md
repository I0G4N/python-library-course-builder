# Complete positive teaching example: from JSON text to reliable settings

This is a teaching-content example, not a complete course JSON fixture, and it
does not replace the field contract in
[`curriculum-contract.md`](curriculum-contract.md). It shows how to turn
readiness evidence, prerequisite teaching, and one graded chapter into
connected, concrete English prose. The phrase "Lab 00 foundation" below is a
legacy teaching label: schema-v3 authoring keeps environment and workflow in
`lab00` and projects these knowledge gaps into one or more `prepNN` units.

A real course must replace this example with the actual target, pinned version,
official sources, selected route, and capstone.

The sample capstone is an offline settings checker. It accepts JSON text and
returns a Python dictionary only when the top-level JSON value is an object.
Later chapters use values from that dictionary to decide whether a local task
is enabled.

This example assumes that the target is a configuration-processing library or
repository and that `json` is an allowed lower-level dependency, not the API
being reimplemented. If the target itself is `json`, put a small hand-written
parser teaching-equivalent in Lab 01 and move the `json.loads` call here to the
Lab 02 official bridge. Downstream work must not import the Lab 01 mini module.

The public behavior is pinned to and cited from the Python 3.13 official
[`json` documentation](https://docs.python.org/3.13/library/json.html).

## Contents

- [Existing evidence and chapter boundary](#existing-evidence-and-chapter-boundary)
- [Lab 00: teach only evidence-backed gaps](#lab-00-teach-only-evidence-backed-gaps)
- [Graded chapter: turn JSON text into validated settings](#graded-chapter-turn-json-text-into-validated-settings)
- [Why this example is complete](#why-this-example-is-complete)

## Existing evidence and chapter boundary

The learner can already define and call functions and can read `str`, `bool`,
and a simple `if`. One behavior question revealed two concrete gaps: the
learner cannot yet predict what happens when a dictionary key is absent, and
they confuse JSON `true` with Python `True`.

The preparatory teaching addresses only those two gaps. It does not add loops,
classes, or file I/O just because those subjects are commonly called basics.

## Lab 00: teach only evidence-backed gaps

### Layer one: general Python gap

#### What you already know

You already know that a function can receive one value and return another.
Use that knowledge as the anchor: the settings checker also receives one value,
but its result contains several named settings such as `enabled` and `retries`.

#### Define the term

A **dictionary** (`dict`) is a Python container that looks up values by key.
Here the key `"enabled"` is the setting name, while the value `True` is the
switch the program will actually use.

This term matters to the current task because the checker must later read
`settings["enabled"]` exactly. It cannot guess which list position happens to
hold the switch.

#### Why this route needs it now

The next chapter converts a JSON object into a Python dictionary. Without a
predictive model for key lookup, the learner could recognize
`json.loads(...)` but still could not explain why the capstone can read the
switch or why a missing key fails.

#### Walk one complete value through the flow

```python
settings = {"enabled": True, "retries": 2}
enabled = settings["enabled"]
print(enabled)
```

The output is:

```text
True
```

The value flow is complete. The dictionary first stores the relationship
between the key `"enabled"` and the Boolean value `True`. Bracket lookup reads
that relationship. The variable `enabled` finally receives `True`.

Lookup does not remove the key and does not mutate the original dictionary.

#### Common misconception and boundary

A common wrong prediction is that `settings["missing"]` returns `None`.
Bracket lookup requires the key to exist, so the observable is `KeyError` when
the key is absent. Only an explicit `settings.get("missing")` uses `None` as
the default result.

#### Recover and check

If `enabled` is required by this route, detect the missing key and give a
task-specific error. The witness below does more than name `KeyError`: it runs
the missing-key input, records the exception, supplies the required key, reruns
the same lookup, and records the recovered result.

##### Required key missing: add it and retry

```python
settings = {"retries": 2}
wrong_input = "enabled"
observed_exception = None
try:
    settings[wrong_input]
except KeyError as exc:
    observed_exception = type(exc).__name__

print(observed_exception)

recovery_input = {"enabled": True, "retries": 2}
recovered_observable = recovery_input["enabled"]
print(recovered_observable)
```

The exact output is:

```text
KeyError
True
```

`recovered_observable is True` proves that the repaired dictionary traveled
through the same bracket lookup. The lesson did not merely write the exception
name into prose.

The knowledge check should therefore show a concrete dictionary and ask the
learner to predict the value or missing-key exception. It should not ask for a
memorized definition of a dictionary.

### Layer two: route-specific library and domain foundation

#### What you already know

You already know that a Python string is text, for example `'hello'`. Connect
that anchor to this route: `'{}'` and `'{' + '"enabled": true' + '}'` are still
`str` values until a parser turns the text into a Python value.

The complete input we use below is `'{' + '"enabled": true, "retries": 2' + '}'`.

#### Define the term

**JSON text** is a string that follows JSON syntax. **Parsing** is the operation
that turns that text into a Python value. A JSON object becomes a Python `dict`,
and JSON `true` becomes Python `True`.

This distinction matters because the capstone receives external text, while
its branch needs a Python value whose keys can be looked up.

#### Why this route needs it now

The next chapter has exactly one new mainline: cross the parsing boundary from
JSON text to a validated Python settings value. Without distinguishing text
from the parsed value, a learner may try dictionary lookup on a string or copy
JSON spelling directly into a Python expression.

#### Walk one complete value through the flow

```python
import json

text = '{"enabled": true, "retries": 2}'
value = json.loads(text)
print(type(text).__name__)
print(value)
```

The output is:

```text
str
{'enabled': True, 'retries': 2}
```

The input starts as `text: str`. `json.loads(text)` reads its characters and
creates a new dictionary. Field names remain unchanged, `true` becomes `True`,
and the number `2` becomes a Python `int`.

After parsing, `text remains unchanged`.

#### Common misconception and boundary

Do not write `{"enabled": true}` as a Python expression. `true` is JSON
notation, not a defined Python name.

Also, valid JSON does not imply that the top-level value is a dictionary.
`["enabled"]` is valid JSON, but it parses to a list and violates this
capstone's top-level-object boundary.

#### Recover and check

These are different failures, so use two witnesses. The first repairs the
Python/JSON Boolean spelling. The second repairs the capstone's required
top-level shape. Each witness reruns the corrected path and prints a recovered
observable.

##### JSON Boolean spelling: use the Python value and retry

```python
wrong_input = "true"
observed_exception = None
try:
    true  # JSON spelling in a Python expression is an undefined name
except NameError as exc:
    observed_exception = type(exc).__name__

print(observed_exception)

recovery_input = {"enabled": True}
recovered_observable = recovery_input["enabled"]
print(recovered_observable)
```

The exact output is:

```text
NameError
True
```

##### Top-level array: replace it with an object and retry

```python
import json


def require_object(text: str) -> dict:
    value = json.loads(text)
    if not isinstance(value, dict):
        raise TypeError("top-level JSON must be an object")
    return value


wrong_input = '["enabled"]'
observed_exception = None
try:
    require_object(wrong_input)
except TypeError as exc:
    observed_exception = f"{type(exc).__name__}: {exc}"

print(observed_exception)

recovery_input = '{"enabled": true}'
recovered_observable = require_object(recovery_input)["enabled"]
print(recovered_observable)
```

The exact output is:

```text
TypeError: top-level JSON must be an object
True
```

The two `True` values prove different recoveries. The Python expression now
uses a valid Boolean value, and the JSON input now parses to a top-level
dictionary. Neither witness stops immediately after replacing the bad input;
both inspect the `enabled` value the route actually needs.

## Graded chapter: turn JSON text into validated settings

This chapter keeps exactly one new knowledge mainline: implement and use
`load_settings` so that the JSON syntax boundary and the capstone's top-level
object boundary form one observable function contract.

### Project problem

The settings checker cannot trust arbitrary text. It must parse the text into
a Python value while rejecting syntax errors and top-level arrays. Otherwise,
the later `settings["enabled"]` either cannot run or fails with an error that
does not explain the project boundary.

### Predict what happens

Start with this mental model: `load_settings` is an entrance with two gates.
The first gate asks whether the input is valid JSON. The second asks whether the
parsed value is the dictionary this project requires. Only a value that passes
both gates reaches the capstone.

Now carry one input through both gates instead of memorizing exception names.

### What are the inputs and outputs?

- The input is `text: str`, specifically `'{' + '"enabled": true, "retries": 2' + '}'`. The caller still owns this string.
- The output is a newly created `dict[str, Any]`, specifically `{'enabled': True, 'retries': 2}`.
- The function does not mutate `text`, read or write files, or mutate external state.
- Invalid JSON syntax makes `json.loads` raise `JSONDecodeError`; repair the text and retry.
- Valid JSON whose top level is not an object makes the function raise `TypeError`; provide a top-level object and retry.

Here, **top level** means the outermost value in the complete JSON document.
The next sentence connects the term to the task: only a top-level object lets
the capstone read `enabled` and `retries` by name.

### Complete runnable example

```python
import json
from typing import Any


def load_settings(text: str) -> dict[str, Any]:
    value = json.loads(text)
    if not isinstance(value, dict):
        raise TypeError("top-level JSON must be an object")
    return value


text = '{"enabled": true, "retries": 2}'
settings = load_settings(text)
print(settings)
print(text)
```

Command:

```bash
python examples/01_load_settings.py
```

Exact output:

```text
{'enabled': True, 'retries': 2}
{"enabled": true, "retries": 2}
```

### Walk one concrete input through the flow

1. `text = '{"enabled": true, "retries": 2}'`; its type is `str`, and ownership remains with the caller.
2. `json.loads(text)` reads that same `text` and produces `value = {'enabled': True, 'retries': 2}`. The value is a new dictionary and `text remains unchanged`.
3. `isinstance(value, dict)` is `True`, so the function returns that new dictionary reference. The capstone reads `settings["enabled"]` and receives Python `True`.

The three transitions do not swap examples or hide the intermediate shape.
They let the learner predict type, ownership, and observable output rather than
accepting a generic phrase such as "parse the configuration."

### Valid case and boundary cases

The valid case uses the same object text:

```python
assert load_settings('{"enabled": true, "retries": 2}') == {
    "enabled": True,
    "retries": 2,
}
```

The first boundary is JSON syntax. `'{' + '"enabled": true,' + '}'` has a
trailing comma, so execution observes `JSONDecodeError`.

The second boundary is the project data shape. `'["enabled"]'` is valid JSON,
but execution observes `TypeError("top-level JSON must be an object")`.

Do not merge both into "bad input." They fail at different gates and require
different recoveries.

### Diagnosis and recovery

The next two examples execute the two boundaries separately. Each records the
actual exception, supplies a concrete recovery input, calls the same
`load_settings` again, and prints the recovered observable.

#### JSON syntax error: repair the text and retry

The counterexample has a trailing comma. `json.loads` rejects it at the first
gate, so the recovery changes the JSON text rather than the top-level-type
check.

```python
import json
from typing import Any


def load_settings(text: str) -> dict[str, Any]:
    value = json.loads(text)
    if not isinstance(value, dict):
        raise TypeError("top-level JSON must be an object")
    return value


wrong_text = '{"enabled": true,}'
observed_exception = None
try:
    load_settings(wrong_text)
except json.JSONDecodeError as exc:
    observed_exception = type(exc).__name__

print(observed_exception)

recovery_text = '{"enabled": true, "retries": 3}'
recovered_observable = load_settings(recovery_text)
print(recovered_observable)
```

Exact output:

```text
JSONDecodeError
{'enabled': True, 'retries': 3}
```

The recovered observable is the new dictionary
`{'enabled': True, 'retries': 3}`. It proves that the corrected text passed
both the syntax gate and the object gate.

#### Top-level array: replace it with an object and retry

The second counterexample is valid JSON, so it passes the syntax gate. Its
parsed value is a list, so the second gate raises a stable `TypeError`.
The recovery changes only the top-level form and reruns the complete path.

```python
import json
from typing import Any


def load_settings(text: str) -> dict[str, Any]:
    value = json.loads(text)
    if not isinstance(value, dict):
        raise TypeError("top-level JSON must be an object")
    return value


wrong_text = '["enabled"]'
observed_exception = None
try:
    load_settings(wrong_text)
except TypeError as exc:
    observed_exception = f"{type(exc).__name__}: {exc}"

print(observed_exception)

recovery_text = '{"enabled": false}'
recovered_observable = load_settings(recovery_text)
print(recovered_observable)
```

Exact output:

```text
TypeError: top-level JSON must be an object
{'enabled': False}
```

The recovered observable is `{'enabled': False}`. It preserves the intended
disabled state and changes only the top-level shape that violated the project
contract.

### Knowledge check

Given `text = '{"enabled": false}'`, which state is correct after
`json.loads` but before the type check?

- A. `value` is still a string and its contents are unchanged.
- B. `value == {'enabled': False}`, while `text` remains the original string.
- C. `value == {'enabled': false}`, and `text` has been mutated.

The correct answer is B. Feedback explains both observable points:
`false -> False` crosses the JSON/Python notation boundary, and parsing does
not mutate the input text. A second diagnostic question should show a top-level
array and ask at which gate it fails and which recovery is valid.

### Coding task and capstone increment

The coding task asks the learner to implement `load_settings(text)`. Public
tests cover a concrete object input and input non-mutation. Hidden tests cover
the trailing comma, top-level array, and different field values.

Every activity maps to the same mainline:

```text
concept_ids: [lab01.c-json-object-boundary]
outcome_ids: [lab01.o-trace-json-boundary, lab01.o-diagnose-json-boundary]
```

After completion, the capstone no longer consumes unchecked text. It calls
`load_settings` first, then gives the returned dictionary's `enabled` value to
the local task switch.

This is an observable product increment: a valid object can enable the task,
while a syntax error or top-level array produces a stable, recoverable failure
at the settings entrance.

## Why this example is complete

Each preparatory gap begins with established knowledge, defines a term,
explains why the selected route needs it now, follows a complete value flow,
shows a misconception or boundary, and executes a recovery check. General
Python and JSON-route foundations are not collapsed into a generic review list.

The graded chapter carries one concrete text through prediction, contract,
execution, boundaries, diagnosis, quiz, coding, and capstone increment while
introducing only one new knowledge mainline.

A real course must still encode this material into source claims, traces,
quizzes, coding questions, and tests required by the specification. This file
only demonstrates the positive shape of connected English teaching.
