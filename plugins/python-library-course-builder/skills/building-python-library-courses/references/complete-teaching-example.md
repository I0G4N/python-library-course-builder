# 完整教学正向示例：从 JSON 文本到可靠配置

这是一份教学内容示例，不是完整课程 JSON fixture，也不替代
[`curriculum-contract.md`](curriculum-contract.md) 的字段约束。它展示如何把 readiness
证据、Lab 00 基础补齐和一章计分内容写成连贯、具体的简体中文。真正生成课程时，应替换成
当前目标、固定版本、官方来源和 capstone 的真实内容。

示例 capstone 是一个离线配置检查器：它接收 JSON 文本，只在顶层是 JSON object 时返回
Python 字典，后续章节再用字典里的值决定本地任务是否启用。

本例假定课程目标是一个配置处理库或仓库，`json` 是允许使用的较低层依赖，而不是正在手写的
目标 API。如果课程目标本身就是 `json`，应把手写解析教学等价物放在 Lab 01，再把本文的
`json.loads` 调用放到 Lab 02 的 official bridge；下游不得导入 Lab 01 的 mini 实现。公开行为
按 Python 3.13 的官方 [`json` 文档](https://docs.python.org/3.13/library/json.html) 固定并引用。

## Contents

- [已有证据与本章边界](#已有证据与本章边界)
- [Lab 00：只补证据指向的缺口](#lab-00只补证据指向的缺口)
- [计分章节：把 JSON 文本变成可验证的配置值](#计分章节把-json-文本变成可验证的配置值)
- [为什么这个示例算完整](#为什么这个示例算完整)

## 已有证据与本章边界

学习者已经能定义并调用函数，也能读懂 `str`、`bool` 和简单 `if`。一次行为题显示了两个
具体缺口：学习者不确定字典缺少键时会发生什么，也会把 JSON 文本里的 `true` 和 Python
代码里的 `True` 混为一谈。Lab 00 只补这两个缺口，不顺带重讲循环、类或文件 I/O。

## Lab 00：只补证据指向的缺口

### 第一层：通用 Python 缺口

#### 你已经会什么

你已经知道函数可以接收一个值并返回另一个值。现在把这个认知当成锚点：配置检查器也会
接收一个值，但返回值里会包含多个有名字的设置，例如 `enabled` 和 `retries`。

#### 先把术语说清楚

**字典**（`dict`）是用键查找值的 Python 容器。这里的键 `"enabled"` 就像设置项的名字，
对应的值 `True` 才是程序真正要使用的开关。这个术语在当前任务中很重要，因为检查器后面
必须准确读取 `settings["enabled"]`，不能靠列表位置猜哪一项是开关。

#### 为什么这条路线现在需要它

下一章会把 JSON object 转换成 Python 字典。如果此时还不能预测键查找，学习者即使看懂
`json.loads(...)`，也无法判断 capstone 为什么能从结果里读出开关，或为什么缺少键会失败。

#### 拿一个完整的值走一遍

```python
settings = {"enabled": True, "retries": 2}
enabled = settings["enabled"]
print(enabled)
```

输出是：

```text
True
```

值的流转是完整的：字典先保存键 `"enabled"` 与布尔值 `True` 的对应关系；方括号查找读取
这个对应关系；变量 `enabled` 最终拿到 `True`。查找不会删除键，也不会修改原字典。

#### 常见误区与边界

一个常见误区是把 `settings["missing"]` 预测成 `None`。方括号查找要求键已经存在；键缺失时
会观察到 `KeyError`。只有显式使用 `settings.get("missing")` 时，默认结果才是 `None`。

#### 怎样恢复并检查

如果 `enabled` 是本路线的必填设置，就先检查键并给出面向任务的错误。下面不只描述
`KeyError`，而是执行缺键输入、记录异常、补上必填键，再重新读取并记录恢复结果。

##### 缺少必填键：补键后重试

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

实际输出是：

```text
KeyError
True
```

`recovered_observable is True` 证明修复后的字典确实重新走过同一个方括号查找，而不是只把
异常名称写进说明。知识检查不问“字典是什么”这种背诵题，而是给出一个具体字典，让学习者
预测查找结果或缺键异常。

### 第二层：路线专属的库与领域基础

#### 你已经会什么

你已经知道 Python 字符串只是文本，例如 `'hello'`。现在把这个锚点连接到本路线：
`'{"enabled": true}'` 仍然只是一个 `str`，此时还不能用 Python 字典的方式读取键。

#### 先把术语说清楚

**JSON 文本**是遵循 JSON 语法的一段字符串；**解析**是把这段文本转换成 Python 值的操作。
JSON object 会变成 Python `dict`，JSON 的 `true` 会变成 Python 的 `True`。这在当前任务中
重要，因为 capstone 接收的是外部文本，而业务判断需要的是可查键的 Python 值。

#### 为什么这条路线现在需要它

下一章的唯一知识主线就是“从 JSON 文本跨过解析边界，得到可验证的 Python 配置值”。如果
不先区分文本和解析后的值，学习者很容易在字符串上查字典键，或者把 JSON 拼写直接复制进
Python 表达式。

#### 拿一个完整的值走一遍

```python
import json

text = '{"enabled": true, "retries": 2}'
value = json.loads(text)
print(type(text).__name__)
print(value)
```

输出是：

```text
str
{'enabled': True, 'retries': 2}
```

输入从 `text: str` 开始；`json.loads(text)` 读取字符并创建一个新的字典；字段名保持不变，
`true` 转换为 `True`，数字 `2` 转换为 Python `int`。解析完成后，`text 保持不变`。

#### 常见误区与边界

不要在 Python 代码中写 `{"enabled": true}`，因为 `true` 是 JSON 记号，不是 Python 名字。
也不要看到“合法 JSON”就推断顶层一定是字典：`["enabled"]` 同样是合法 JSON，但解析结果
是列表，不符合本 capstone 的“顶层必须是 object”边界。

#### 怎样恢复并检查

这里有两个不同问题，所以分别执行两个见证：第一个修正 Python/JSON 布尔拼写，第二个修正
capstone 的顶层形态。每个见证都重新执行修正后的路径并打印 recovered observable。

##### JSON 布尔拼写：改用 Python 值后重试

```python
wrong_input = "true"
observed_exception = None
try:
    true  # JSON 的拼写放进 Python 表达式会被当成未定义名字
except NameError as exc:
    observed_exception = type(exc).__name__

print(observed_exception)

recovery_input = {"enabled": True}
recovered_observable = recovery_input["enabled"]
print(recovered_observable)
```

实际输出是：

```text
NameError
True
```

##### 顶层数组：改成 object 后重试

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

实际输出是：

```text
TypeError: top-level JSON must be an object
True
```

两个 `True` 分别证明 Python 表达式已使用正确布尔值、JSON 输入也已重新解析为顶层字典；它们
不是把错误输入换掉后就停止，而是继续检查了本路线真正要读取的 `enabled` 值。

## 计分章节：把 JSON 文本变成可验证的配置值

这一章只保留一条新知识主线：实现并使用 `load_settings`，把 JSON 语法边界和 capstone 的
顶层 object 边界合成一个可观察的函数契约。

### 项目问题

配置检查器不能直接信任一段文本。它需要把文本解析为 Python 值，同时拒绝语法错误和
顶层数组，否则后续的 `settings["enabled"]` 要么无法执行，要么产生与项目无关的错误。

### 先预测会发生什么

先这样理解：`load_settings` 像一道有两扇门的入口。第一扇门检查“这是不是合法 JSON”，
第二扇门检查“解析结果是不是本项目需要的字典”。只有两扇门都通过，字典才会交给
capstone。接下来用同一个输入走过两扇门，而不是先背异常名称。

### 输入和输出是什么

- 输入是 `text: str`，具体例子是 `'{"enabled": true, "retries": 2}'`。调用者仍然拥有这个字符串。
- 输出是一个新建的 `dict[str, Any]`，具体结果是 `{'enabled': True, 'retries': 2}`。
- 函数不修改 `text`，不读写文件，也不修改外部状态。
- JSON 语法错误会由 `json.loads` 抛出 `JSONDecodeError`；恢复方式是修正文本后重试。
- 合法 JSON 的顶层不是 object 时，函数抛出 `TypeError`；恢复方式是提供顶层 object 后重试。

这里的“顶层”指整段 JSON 最外面的那个值。定义完这个术语，马上连接当前任务：只有最外层
是 object，capstone 才能按名字读取 `enabled` 和 `retries`。

### 完整可运行例子

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

命令：

```bash
python examples/01_load_settings.py
```

精确输出：

```text
{'enabled': True, 'retries': 2}
{"enabled": true, "retries": 2}
```

### 同一个值怎样完整流转

1. `text = '{"enabled": true, "retries": 2}'`，类型是 `str`，所有权仍在调用者。
2. `json.loads(text)` 读取同一个 `text`，产生
   `value = {'enabled': True, 'retries': 2}`；此时 `value` 是新字典，`text 保持不变`。
3. `isinstance(value, dict)` 得到 `True`，所以函数返回同一个新字典引用；capstone 随后读取
   `settings["enabled"]`，得到 Python 布尔值 `True`。

这三个步骤没有更换示例，也没有跳过中间形态。学习者可以据此预测类型、所有权和可观察
输出，而不是只看到一句“解析配置”。

### 有效案例与边界案例

有效案例仍使用同一个对象文本：

```python
assert load_settings('{"enabled": true, "retries": 2}') == {
    "enabled": True,
    "retries": 2,
}
```

第一个边界是 JSON 语法：`'{"enabled": true,}'` 多了尾逗号，执行时观察到
`JSONDecodeError`。第二个边界是项目数据形态：`'["enabled"]'` 语法合法，却会观察到
`TypeError("top-level JSON must be an object")`。两个边界不能合并成“输入不对”，因为它们
发生在不同的门，恢复动作也不同。

### 诊断与恢复

下面把两个边界分开执行。每段代码都能单独保存并运行；它先记录反例的实际异常，再替换成
具体的恢复输入，重新调用同一个 `load_settings`，最后打印恢复后的可观察值。

#### JSON 语法错误：修正文本后重试

第一段反例多了尾逗号。`json.loads` 在第一扇门就拒绝它，因此恢复动作是修正 JSON 文本，
而不是改动顶层类型检查。

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

实际输出是：

```text
JSONDecodeError
{'enabled': True, 'retries': 3}
```

这里记录的 recovered observable 是新字典 `{'enabled': True, 'retries': 3}`；它证明修正后的
文本已经重新穿过语法门和 object 门，而不只是把异常名称写进说明。

#### 顶层数组：改成 object 后重试

第二段反例是合法 JSON，所以它会穿过语法门；但解析结果是列表，第二扇门会稳定地抛出
`TypeError`。恢复动作是把最外层数组改成 object，再重跑完整路径。

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

实际输出是：

```text
TypeError: top-level JSON must be an object
{'enabled': False}
```

这里记录的 recovered observable 是 `{'enabled': False}`。它同时证明恢复输入保持了原来想
表达的关闭状态，只改变不符合项目契约的顶层形态。

### 知识检查

给定 `text = '{"enabled": false}'`，`json.loads` 之后、类型检查之前，哪个状态正确？

- A. `value` 仍是字符串，内容不变。
- B. `value == {'enabled': False}`，而 `text` 仍是原字符串。
- C. `value == {'enabled': false}`，并且 `text` 被修改。

正确答案是 B。反馈说明 `false -> False` 的跨语言转换和“解析不修改输入”两个可观察点，
而不只写“回答正确”。诊断题再给出顶层数组，让学习者指出失败发生在第二扇门并选择恢复输入。

### 编码任务与 capstone 增量

编码题要求实现上面的 `load_settings(text)`，公开测试覆盖具体 object 输入和不修改输入；隐藏
测试覆盖尾逗号、顶层数组以及不同字段值。活动都映射到同一主线：

```text
concept_ids: [lab01.c-json-object-boundary]
outcome_ids: [lab01.o-trace-json-boundary, lab01.o-diagnose-json-boundary]
```

完成后，capstone 不再接收未经检查的文本，而是先调用 `load_settings`，再把返回字典中的
`enabled` 交给本地任务开关。这是可观察的产品增量：合法 object 能启用任务，语法错误或顶层
数组会在配置入口处给出稳定、可恢复的失败。

## 为什么这个示例算完整

Lab 00 的每个缺口都从已有认知开始，定义术语，说明当前路线为什么需要它，再给出完整值流、
误区/边界和恢复检查；通用 Python 与 JSON 路线基础没有混在一个“复习”列表里。计分章则用
同一具体文本贯穿预测、契约、运行、边界、诊断、quiz、coding 和 capstone 增量，并且只引入
一条新主线。真正课程还必须把这些内容编码进规范要求的 source claims、trace、quiz、question
和 tests；本示例只负责展示教学表达的正向形状。
