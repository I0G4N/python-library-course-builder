import { Fragment, type ReactNode } from "react";

import { PythonCodeBlock } from "./PythonCode";

type LessonPrerequisite = {
  id: string;
  title: string;
  why: string;
  refresh: string;
};

type LessonOutcome = { id: string; text: string };

type LessonSourceClaim = {
  source_id: string;
  claim: string;
  status: "documented" | "implementation";
};

type OperationalContractKind =
  | "api"
  | "mechanism"
  | "formula"
  | "lifecycle"
  | "data-model";

type OperationalInput = {
  name: string;
  meaning: string;
  form: string;
  example: string;
  constraints: string[];
};

type OperationalOutput = {
  name: string;
  meaning: string;
  form: string;
  example: string;
};

type OperationalFailure = {
  condition: string;
  observable: string;
  recovery: string;
};

type OperationalContract = {
  kind: OperationalContractKind;
  forms: string[];
  inputs: OperationalInput[];
  outputs: OperationalOutput[];
  effects: string[];
  failure_modes: OperationalFailure[];
};

type LessonTraceStep = {
  id: string;
  concept_ids: string[];
  input_state: string;
  operation: string;
  output_state: string;
  explanation: string;
};

type LessonConcept = {
  id: string;
  name: string;
  definition: string;
  purpose: string;
  mechanism: string[];
  mental_model: string;
  design_reasons: string[];
  benefits: string[];
  tradeoffs: string[];
  invariants: string[];
  boundaries: string[];
  pitfalls: string[];
  source_claims: LessonSourceClaim[];
  operational_contract?: OperationalContract;
};

type LessonExample = {
  id: string;
  title: string;
  kind: "runnable" | "diagnostic";
  explanation: string;
  concept_ids: string[];
  outcome_ids: string[];
  path?: string;
  code?: string;
  command?: string;
  expected_output?: string;
  wrong_code?: string;
  symptom?: string;
  cause?: string;
  fix_code?: string;
  trace?: LessonTraceStep[];
};

export type StudyMinutes =
  | { tier: "orientation"; min: 15; max: 30; reason?: never }
  | { tier: "standard"; min: 30; max: 45; reason?: never }
  | { tier: "foundation" | "extended"; min: 45; max: 60; reason: string };

export type PracticeLink = {
  concept_id: string;
  kind: "knowledge-check" | "coding-question";
  item_id: string;
  title: string;
};

export type LessonOutline = {
  prerequisites: LessonPrerequisite[];
  problem: {
    context: string;
    naive_approach: string;
    failure: string;
  };
  outcomes: LessonOutcome[];
  concepts: LessonConcept[];
  examples: LessonExample[];
  capstone_bridge: {
    input: string;
    output: string;
    increment: string;
    next: string;
  };
  summary: string[];
};

export type CourseContentItem = {
  id: string;
  title: string;
  lesson: string;
  lesson_outline?: LessonOutline;
  sources?: Array<{ id: string; title: string; url: string }>;
  concepts?: string[];
  capstone_increment?: string;
  study_minutes?: StudyMinutes;
  practice_links?: PracticeLink[];
};

export type CourseLessonProps = {
  content: CourseContentItem;
  onPractice?: (link: PracticeLink) => void;
};

const SAFE_LINK = /^https?:\/\//i;
const INLINE_TOKEN = /(\[[^\]]+\]\([^)]+\)|`[^`]+`|\*\*[^*]+\*\*)/g;

function inlineMarkdown(value: string): ReactNode[] {
  return value.split(INLINE_TOKEN).filter(Boolean).map((part, index) => {
    if (part.startsWith("`") && part.endsWith("`")) {
      return <code key={index}>{part.slice(1, -1)}</code>;
    }
    if (part.startsWith("**") && part.endsWith("**")) {
      return <strong key={index}>{part.slice(2, -2)}</strong>;
    }
    const link = /^\[([^\]]+)\]\(([^)]+)\)$/.exec(part);
    if (link) {
      const [, label, href] = link;
      return SAFE_LINK.test(href) ? (
        <a key={index} href={href} target="_blank" rel="noopener noreferrer">
          {label}
        </a>
      ) : (
        <span key={index}>{label}</span>
      );
    }
    return <Fragment key={index}>{part}</Fragment>;
  });
}

function tableCells(line: string): string[] {
  return line.trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map((cell) => cell.trim());
}

function markdownBlocks(markdown: string): ReactNode[] {
  const lines = markdown.replace(/\r\n/g, "\n").split("\n");
  const blocks: ReactNode[] = [];
  let index = 0;
  while (index < lines.length) {
    const line = lines[index];
    if (!line.trim()) {
      index += 1;
      continue;
    }
    const fence = /^```([\w+-]*)\s*$/.exec(line);
    if (fence) {
      const language = fence[1].toLowerCase();
      const body: string[] = [];
      index += 1;
      while (index < lines.length && !/^```\s*$/.test(lines[index])) {
        body.push(lines[index]);
        index += 1;
      }
      if (index < lines.length) index += 1;
      const code = body.join("\n");
      blocks.push(
        language === "python" || language === "py" ? (
          <PythonCodeBlock key={`code-${blocks.length}`} code={code} ariaLabel="讲义 Python 示例" />
        ) : (
          <pre key={`code-${blocks.length}`} className="plain-code"><code>{code}</code></pre>
        ),
      );
      continue;
    }
    const heading = /^(#{1,4})\s+(.+)$/.exec(line);
    if (heading) {
      const text = inlineMarkdown(heading[2]);
      const level = heading[1].length;
      blocks.push(
        level <= 1 ? <h2 key={`heading-${blocks.length}`}>{text}</h2>
          : level === 2 ? <h3 key={`heading-${blocks.length}`}>{text}</h3>
            : <h4 key={`heading-${blocks.length}`}>{text}</h4>,
      );
      index += 1;
      continue;
    }
    if (/^>\s?/.test(line)) {
      const quote: string[] = [];
      while (index < lines.length && /^>\s?/.test(lines[index])) {
        quote.push(lines[index].replace(/^>\s?/, ""));
        index += 1;
      }
      blocks.push(<blockquote key={`quote-${blocks.length}`}>{inlineMarkdown(quote.join(" "))}</blockquote>);
      continue;
    }
    if (/^\s*\|?.+\|.+\|?\s*$/.test(line) && /^\s*\|?\s*:?-{3,}/.test(lines[index + 1] ?? "")) {
      const headers = tableCells(line);
      index += 2;
      const rows: string[][] = [];
      while (index < lines.length && /^\s*\|?.+\|.+\|?\s*$/.test(lines[index])) {
        rows.push(tableCells(lines[index]));
        index += 1;
      }
      blocks.push(
        <div className="table-wrap" key={`table-${blocks.length}`}>
          <table><thead><tr>{headers.map((cell, cellIndex) => <th key={cellIndex}>{inlineMarkdown(cell)}</th>)}</tr></thead>
            <tbody>{rows.map((row, rowIndex) => <tr key={rowIndex}>{row.map((cell, cellIndex) => <td key={cellIndex}>{inlineMarkdown(cell)}</td>)}</tr>)}</tbody>
          </table>
        </div>,
      );
      continue;
    }
    if (/^[-*]\s+/.test(line)) {
      const items: string[] = [];
      while (index < lines.length && /^[-*]\s+/.test(lines[index])) {
        items.push(lines[index].replace(/^[-*]\s+/, ""));
        index += 1;
      }
      blocks.push(<ul key={`list-${blocks.length}`}>{items.map((item, itemIndex) => <li key={itemIndex}>{inlineMarkdown(item)}</li>)}</ul>);
      continue;
    }
    if (/^\d+\.\s+/.test(line)) {
      const items: string[] = [];
      while (index < lines.length && /^\d+\.\s+/.test(lines[index])) {
        items.push(lines[index].replace(/^\d+\.\s+/, ""));
        index += 1;
      }
      blocks.push(<ol key={`list-${blocks.length}`}>{items.map((item, itemIndex) => <li key={itemIndex}>{inlineMarkdown(item)}</li>)}</ol>);
      continue;
    }
    if (/^---+$/.test(line.trim())) {
      blocks.push(<hr key={`rule-${blocks.length}`} />);
      index += 1;
      continue;
    }
    const paragraph = [line.trim()];
    index += 1;
    while (
      index < lines.length && lines[index].trim() &&
      !/^(#{1,4})\s+|^```|^>\s?|^[-*]\s+|^\d+\.\s+|^---+$/.test(lines[index])
    ) {
      paragraph.push(lines[index].trim());
      index += 1;
    }
    blocks.push(<p key={`paragraph-${blocks.length}`}>{inlineMarkdown(paragraph.join(" "))}</p>);
  }
  return blocks;
}

function BulletList({ items }: { items: string[] }) {
  return <ul>{items.map((item, index) => <li key={index}>{inlineMarkdown(item)}</li>)}</ul>;
}

function formatStudyMinutes(study: StudyMinutes): string {
  return `${study.min}–${study.max} 分钟`;
}

function OperationalContractView({ concept }: { concept: LessonConcept }) {
  const operational_contract = concept.operational_contract;
  if (!operational_contract) return null;
  return (
    <section className="operational-contract" aria-label={`${concept.name} 的输入输出契约`}>
      <h4>输入和输出是什么</h4>
      <p><strong>可用形式：</strong>{operational_contract.forms.map((form) => <code key={form}>{form}</code>)}</p>
      <h5>输入</h5>
      {operational_contract.inputs.map((input) => (
        <dl key={input.name}>
          <dt>{input.name}</dt><dd>{input.meaning}</dd>
          <dt>形式</dt><dd><code>{input.form}</code></dd>
          <dt>具体例子</dt><dd><code>{input.example}</code></dd>
          {input.constraints.length ? <><dt>约束</dt><dd><BulletList items={input.constraints} /></dd></> : null}
        </dl>
      ))}
      <h5>输出</h5>
      {operational_contract.outputs.map((output) => (
        <dl key={output.name}>
          <dt>{output.name}</dt><dd>{output.meaning}</dd>
          <dt>形式</dt><dd><code>{output.form}</code></dd>
          <dt>具体例子</dt><dd><code>{output.example}</code></dd>
        </dl>
      ))}
      <h5>可观察影响</h5>
      <BulletList items={operational_contract.effects} />
      <h5>失败时会发生什么</h5>
      {operational_contract.failure_modes.map((failure, index) => (
        <dl key={index}>
          <dt>条件</dt><dd>{failure.condition}</dd>
          <dt>可观察结果</dt><dd>{failure.observable}</dd>
          <dt>恢复方式</dt><dd>{failure.recovery}</dd>
        </dl>
      ))}
    </section>
  );
}

function ConceptOverview({
  concept,
  practice,
  onPractice,
}: {
  concept: LessonConcept;
  practice?: PracticeLink;
  onPractice?: (link: PracticeLink) => void;
}) {
  return (
    <article className="lesson-concept-overview" aria-labelledby={`${concept.id}-overview-title`}>
      <h3 id={`${concept.id}-overview-title`}>{concept.name}</h3>
      <p><strong>定义：</strong>{concept.definition}</p>
      <p><strong>它解决什么：</strong>{concept.purpose}</p>
      <h4>先这样理解</h4>
      <p>{concept.mental_model}</p>
      <OperationalContractView concept={concept} />
      {practice ? (
        <button
          type="button"
          className="practice-action"
          onClick={() => onPractice?.(practice)}
        >
          <span>先做这个练习</span>
          <strong>{practice.title}</strong>
        </button>
      ) : null}
    </article>
  );
}

function ConceptDeepDive({ concept }: { concept: LessonConcept }) {
  return (
    <section className="lesson-concept" aria-labelledby={`${concept.id}-title`}>
      <h4 id={`${concept.id}-title`}>{concept.name}</h4>
      <h4>运行过程</h4>
      <ol>{concept.mechanism.map((step, index) => <li key={index}>{inlineMarkdown(step)}</li>)}</ol>
      <div className="lesson-tradeoff-grid">
        <section><h4>为什么这样设计</h4><BulletList items={concept.design_reasons} /></section>
        <section><h4>带来的好处</h4><BulletList items={concept.benefits} /></section>
        <section><h4>要付出的代价</h4><BulletList items={concept.tradeoffs} /></section>
        <section><h4>必须保持的条件</h4><BulletList items={concept.invariants} /></section>
        <section><h4>适用边界</h4><BulletList items={concept.boundaries} /></section>
        <section><h4>常见误区</h4><BulletList items={concept.pitfalls} /></section>
      </div>
      <div className="lesson-claims" aria-label="本概念的来源依据">
        {concept.source_claims.map((claim, index) => (
          <p key={`${claim.source_id}-${index}`}>
            <span>{claim.status === "documented" ? "公开契约" : "实现细节"}</span>
            {claim.claim}
          </p>
        ))}
      </div>
    </section>
  );
}

function StructuredLesson({
  outline,
  studyMinutes,
  practiceLinks,
  onPractice,
}: {
  outline: LessonOutline;
  studyMinutes?: StudyMinutes;
  practiceLinks: PracticeLink[];
  onPractice?: (link: PracticeLink) => void;
}) {
  const runnableExamples = outline.examples.filter((example) => example.kind === "runnable");
  const diagnosticExamples = outline.examples.filter((example) => example.kind === "diagnostic");
  const practiceLinksByConcept = new Map(
    practiceLinks.map((practice) => [practice.concept_id, practice]),
  );
  return (
    <>
      <section className="lesson-beginner-core">
        {studyMinutes ? (
          <aside className="study-time">
            <strong>预计学习时间：{formatStudyMinutes(studyMinutes)}</strong>
            {studyMinutes.reason ? <span>{studyMinutes.reason}</span> : null}
          </aside>
        ) : null}
        <h2>学习前先确认</h2>
        <div className="lesson-prerequisites">
          {outline.prerequisites.map((item) => (
            <article key={item.id}>
              <h3>{item.title}</h3>
              <p><strong>为什么需要：</strong>{item.why}</p>
              <p><strong>快速复习：</strong>{item.refresh}</p>
            </article>
          ))}
        </div>

        <h2>本章要解决的问题</h2>
        <p>{outline.problem.context}</p>
        <blockquote>
          <strong>看似简单的做法：</strong> {outline.problem.naive_approach}<br />
          <strong>它为什么会失败：</strong> {outline.problem.failure}
        </blockquote>

        <h2>学完你将能够</h2>
        <ul>{outline.outcomes.map((outcome) => <li key={outcome.id}>{outcome.text}</li>)}</ul>

        <h2>先认识本章概念</h2>
        <div className="lesson-concept-overviews">
          {outline.concepts.map((concept) => (
            <ConceptOverview
              key={concept.id}
              concept={concept}
              practice={practiceLinksByConcept.get(concept.id)}
              onPractice={onPractice}
            />
          ))}
        </div>

        <h2>讲义可运行示例</h2>
        {runnableExamples.map((example) => (
          <article className="lesson-runnable" key={example.id}>
            <h3>{example.title}</h3>
            <p>{example.explanation}</p>
            {example.code ? <PythonCodeBlock code={example.code} ariaLabel={`${example.title} Python 示例`} /> : null}
            <dl>
              <dt>运行</dt><dd><code>{example.command}</code></dd>
              <dt>预期</dt><dd><code>{example.expected_output}</code></dd>
            </dl>
            {example.trace?.length ? (
              <section className="lesson-trace" aria-label={`${example.title} 的具体执行轨迹`}>
                <h4>拿一个具体输入走一遍</h4>
                <ol>
                  {example.trace.map((step) => (
                    <li key={step.id}>
                      <dl>
                        <dt>输入状态</dt><dd>{step.input_state}</dd>
                        <dt>执行动作</dt><dd>{step.operation}</dd>
                        <dt>输出状态</dt><dd>{step.output_state}</dd>
                        <dt>为什么</dt><dd>{step.explanation}</dd>
                      </dl>
                    </li>
                  ))}
                </ol>
              </section>
            ) : null}
          </article>
        ))}
      </section>

      <details className="lesson-deep-dive">
        <summary>运行细节：深入原理与设计取舍</summary>
        <div className="lesson-disclosure-body">
          {outline.concepts.map((concept) => <ConceptDeepDive key={concept.id} concept={concept} />)}
        </div>
      </details>

      <details className="lesson-deep-dive lesson-diagnostic">
        <summary>错误现象、原因与修复</summary>
        <div className="lesson-disclosure-body">
          {diagnosticExamples.map((example) => (
            <article key={example.id}>
              <h3>{example.title}</h3>
              <p>{example.explanation}</p>
              <h4>错误代码</h4>
              {example.wrong_code ? <PythonCodeBlock code={example.wrong_code} ariaLabel={`${example.title} 错误代码`} /> : null}
              <p><strong>你会看到：</strong>{example.symptom}</p>
              <p><strong>根本原因：</strong>{example.cause}</p>
              <h4>修复代码</h4>
              {example.fix_code ? <PythonCodeBlock code={example.fix_code} ariaLabel={`${example.title} 修复代码`} /> : null}
            </article>
          ))}
        </div>
      </details>

      <section className="lesson-bridge" aria-label="本章与累计项目的连接">
        <h2>把这一章接回累计项目</h2>
        <dl>
          <dt>输入</dt><dd>{outline.capstone_bridge.input}</dd>
          <dt>输出</dt><dd>{outline.capstone_bridge.output}</dd>
          <dt>本章增量</dt><dd>{outline.capstone_bridge.increment}</dd>
          <dt>下一章</dt><dd>{outline.capstone_bridge.next}</dd>
        </dl>
        <h3>本章小结</h3>
        <BulletList items={outline.summary} />
      </section>
    </>
  );
}

export function CourseLesson({ content, onPractice }: CourseLessonProps) {
  return (
    <article className="course-lesson" aria-label={`${content.title} 讲义`}>
      {content.concepts?.length ? (
        <div className="concept-row" aria-label="本章概念">
          {content.concepts.map((concept) => <span key={concept}>{concept}</span>)}
        </div>
      ) : null}
      {content.lesson_outline
        ? (
            <StructuredLesson
              outline={content.lesson_outline}
              studyMinutes={content.study_minutes}
              practiceLinks={content.practice_links ?? []}
              onPractice={onPractice}
            />
          )
        : markdownBlocks(content.lesson)}
      {content.capstone_increment ? (
        <aside className="capstone-note"><strong>CAPSTONE</strong><span>{content.capstone_increment}</span></aside>
      ) : null}
      {content.sources?.length ? (
        <details className="source-list">
          <summary>依据与延伸：官方参考资料</summary>
          <div aria-label="参考资料">
            {content.sources.map((source) => (
              <a key={source.id} href={source.url} target="_blank" rel="noopener noreferrer">{source.title}</a>
            ))}
          </div>
        </details>
      ) : null}
    </article>
  );
}
