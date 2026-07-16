import { Fragment, type ReactNode } from "react";

import { PythonCodeBlock } from "./PythonCode";
import {
  consumeMarkdownList,
  extractLessonTerms,
  extractTutorialHeadings,
  type LessonTerm,
  type TutorialHeading,
} from "./lessonGuide.mjs";
import {
  courseCopy,
  type CourseCopy,
  type CourseLanguage,
} from "./courseLocale.mjs";

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
  lesson_format?: "tutorial-markdown-v1";
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
  language: CourseLanguage;
  onPractice?: (link: PracticeLink) => void;
};

const SAFE_EXTERNAL_LINK = /^https?:\/\//i;
const SAFE_FRAGMENT_LINK = /^#[\p{Letter}\p{Number}_:.\-]+$/u;
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
      if (SAFE_FRAGMENT_LINK.test(href)) {
        return <a key={index} href={href}>{label}</a>;
      }
      return SAFE_EXTERNAL_LINK.test(href) ? (
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

function markdownBlocks(markdown: string, t: CourseCopy): ReactNode[] {
  const lines = markdown.replace(/\r\n/g, "\n").split("\n");
  const headings = extractTutorialHeadings(markdown);
  const blocks: ReactNode[] = [];
  let index = 0;
  let headingIndex = 0;
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
          <PythonCodeBlock key={`code-${blocks.length}`} code={code} ariaLabel={t.lessonPythonExample} />
        ) : (
          <pre key={`code-${blocks.length}`} className="plain-code"><code>{code}</code></pre>
        ),
      );
      continue;
    }
    const heading = /^(#{1,6})\s+(.+?)\s*#*\s*$/.exec(line);
    if (heading) {
      const text = inlineMarkdown(heading[2]);
      const level = heading[1].length;
      const id = headings[headingIndex]?.id ?? `section-${headingIndex + 1}`;
      headingIndex += 1;
      blocks.push(
        level === 1 ? <h1 id={id} key={id}>{text}</h1>
          : level === 2 ? <h2 id={id} key={id}>{text}</h2>
            : level === 3 ? <h3 id={id} key={id}>{text}</h3>
              : level === 4 ? <h4 id={id} key={id}>{text}</h4>
                : level === 5 ? <h5 id={id} key={id}>{text}</h5>
                  : <h6 id={id} key={id}>{text}</h6>,
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
    const list = consumeMarkdownList(lines, index);
    if (list) {
      const items = list.items.map((item, itemIndex) => (
        <li key={itemIndex}>{inlineMarkdown(item)}</li>
      ));
      blocks.push(
        list.ordered
          ? <ol key={`list-${blocks.length}`} start={list.start}>{items}</ol>
          : <ul key={`list-${blocks.length}`}>{items}</ul>,
      );
      index = list.nextIndex;
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
      !/^(#{1,6})\s+|^```|^>\s?|^ {0,3}(?:[-+*]|\d+[.)])[ \t]+|^---+$/.test(lines[index])
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

function formatStudyMinutes(study: StudyMinutes, t: CourseCopy): string {
  return t.studyMinutes(study.min, study.max);
}

function guideCopy(language: CourseLanguage) {
  return language === "zh-CN"
    ? {
        label: "章节导览",
        contents: "本章目录",
        terms: "术语索引",
        emptyContents: "本章没有单独的小节。",
      }
    : {
        label: "Chapter guide",
        contents: "On this page",
        terms: "Terminology",
        emptyContents: "This chapter has no separate sections.",
      };
}

function HeadingGuide({ headings }: { headings: TutorialHeading[] }) {
  return (
    <ol className="chapter-toc-list">
      {headings.map((heading) => (
        <li key={heading.id} data-level={heading.level}>
          <a href={`#${heading.id}`}>{heading.title}</a>
        </li>
      ))}
    </ol>
  );
}

function TermGuide({ terms }: { terms: LessonTerm[] }) {
  return (
    <dl className="chapter-term-list">
      {terms.map((term) => (
        <div key={term.id}>
          <dt>{term.name}</dt>
          <dd>{term.definition}</dd>
        </div>
      ))}
    </dl>
  );
}

export function ChapterGuide({
  content,
  language,
}: {
  content: CourseContentItem;
  language: CourseLanguage;
}) {
  const copy = guideCopy(language);
  const headings = content.lesson_format === "tutorial-markdown-v1"
    ? extractTutorialHeadings(content.lesson)
    : [];
  const terms = extractLessonTerms(content.lesson_outline);
  return (
    <nav className="chapter-guide" aria-label={copy.label}>
      <section className="chapter-guide-section" aria-labelledby="chapter-toc-title">
        <h3 id="chapter-toc-title">{copy.contents}</h3>
        {headings.length ? <HeadingGuide headings={headings} /> : <p>{copy.emptyContents}</p>}
      </section>
      {terms.length ? (
        <section className="chapter-guide-section chapter-terms" aria-labelledby="chapter-terms-title">
          <h3 id="chapter-terms-title">{copy.terms}</h3>
          <TermGuide terms={terms} />
        </section>
      ) : null}
    </nav>
  );
}

function OperationalContractView({ concept, t }: { concept: LessonConcept; t: CourseCopy }) {
  const operational_contract = concept.operational_contract;
  if (!operational_contract) return null;
  return (
    <section className="operational-contract" aria-label={t.inputOutputContract(concept.name)}>
      <h4>{t.inputOutputHeading}</h4>
      <p><strong>{t.availableForms}</strong>{operational_contract.forms.map((form) => <code key={form}>{form}</code>)}</p>
      <h5>{t.input}</h5>
      {operational_contract.inputs.map((input) => (
        <dl key={input.name}>
          <dt>{input.name}</dt><dd>{input.meaning}</dd>
          <dt>{t.form}</dt><dd><code>{input.form}</code></dd>
          <dt>{t.concreteExample}</dt><dd><code>{input.example}</code></dd>
          {input.constraints.length ? <><dt>{t.constraints}</dt><dd><BulletList items={input.constraints} /></dd></> : null}
        </dl>
      ))}
      <h5>{t.output}</h5>
      {operational_contract.outputs.map((output) => (
        <dl key={output.name}>
          <dt>{output.name}</dt><dd>{output.meaning}</dd>
          <dt>{t.form}</dt><dd><code>{output.form}</code></dd>
          <dt>{t.concreteExample}</dt><dd><code>{output.example}</code></dd>
        </dl>
      ))}
      <h5>{t.observableEffects}</h5>
      <BulletList items={operational_contract.effects} />
      <h5>{t.failureBehavior}</h5>
      {operational_contract.failure_modes.map((failure, index) => (
        <dl key={index}>
          <dt>{t.condition}</dt><dd>{failure.condition}</dd>
          <dt>{t.observableResult}</dt><dd>{failure.observable}</dd>
          <dt>{t.recovery}</dt><dd>{failure.recovery}</dd>
        </dl>
      ))}
    </section>
  );
}

function ConceptOverview({
  concept,
  practice,
  onPractice,
  t,
}: {
  concept: LessonConcept;
  practice?: PracticeLink;
  onPractice?: (link: PracticeLink) => void;
  t: CourseCopy;
}) {
  return (
    <article className="lesson-concept-overview" aria-labelledby={`${concept.id}-overview-title`}>
      <h3 id={`${concept.id}-overview-title`}>{concept.name}</h3>
      <p><strong>{t.definition}</strong>{concept.definition}</p>
      <p><strong>{t.purpose}</strong>{concept.purpose}</p>
      <h4>{t.mentalModel}</h4>
      <p>{concept.mental_model}</p>
      <OperationalContractView concept={concept} t={t} />
      {practice ? (
        <button
          type="button"
          className="practice-action"
          onClick={() => onPractice?.(practice)}
        >
          <span>{t.practiceFirst}</span>
          <strong>{practice.title}</strong>
        </button>
      ) : null}
    </article>
  );
}

function ConceptDeepDive({ concept, t }: { concept: LessonConcept; t: CourseCopy }) {
  return (
    <section className="lesson-concept" aria-labelledby={`${concept.id}-title`}>
      <h4 id={`${concept.id}-title`}>{concept.name}</h4>
      <h4>{t.runtimeProcess}</h4>
      <ol>{concept.mechanism.map((step, index) => <li key={index}>{inlineMarkdown(step)}</li>)}</ol>
      <div className="lesson-tradeoff-grid">
        <section><h4>{t.designReasons}</h4><BulletList items={concept.design_reasons} /></section>
        <section><h4>{t.benefits}</h4><BulletList items={concept.benefits} /></section>
        <section><h4>{t.tradeoffs}</h4><BulletList items={concept.tradeoffs} /></section>
        <section><h4>{t.invariants}</h4><BulletList items={concept.invariants} /></section>
        <section><h4>{t.boundaries}</h4><BulletList items={concept.boundaries} /></section>
        <section><h4>{t.pitfalls}</h4><BulletList items={concept.pitfalls} /></section>
      </div>
      <div className="lesson-claims" aria-label={t.sourceBasis}>
        {concept.source_claims.map((claim, index) => (
          <p key={`${claim.source_id}-${index}`}>
            <span>{claim.status === "documented" ? t.documentedContract : t.implementationDetail}</span>
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
  t,
}: {
  outline: LessonOutline;
  studyMinutes?: StudyMinutes;
  practiceLinks: PracticeLink[];
  onPractice?: (link: PracticeLink) => void;
  t: CourseCopy;
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
            <strong>{t.estimatedStudyTime}{formatStudyMinutes(studyMinutes, t)}</strong>
            {studyMinutes.reason ? <span>{studyMinutes.reason}</span> : null}
          </aside>
        ) : null}
        <h2>{t.studyPrerequisites}</h2>
        <div className="lesson-prerequisites">
          {outline.prerequisites.map((item) => (
            <article key={item.id}>
              <h3>{item.title}</h3>
              <p><strong>{t.whyNeeded}</strong>{item.why}</p>
              <p><strong>{t.quickReview}</strong>{item.refresh}</p>
            </article>
          ))}
        </div>

        <h2>{t.chapterProblem}</h2>
        <p>{outline.problem.context}</p>
        <blockquote>
          <strong>{t.naiveApproach}</strong> {outline.problem.naive_approach}<br />
          <strong>{t.whyItFails}</strong> {outline.problem.failure}
        </blockquote>

        <h2>{t.outcomes}</h2>
        <ul>{outline.outcomes.map((outcome) => <li key={outcome.id}>{outcome.text}</li>)}</ul>

        <h2>{t.conceptsFirst}</h2>
        <div className="lesson-concept-overviews">
          {outline.concepts.map((concept) => (
            <ConceptOverview
              key={concept.id}
              concept={concept}
              practice={practiceLinksByConcept.get(concept.id)}
              onPractice={onPractice}
              t={t}
            />
          ))}
        </div>

        <h2>{t.runnableExamples}</h2>
        {runnableExamples.map((example) => (
          <article className="lesson-runnable" key={example.id}>
            <h3>{example.title}</h3>
            <p>{example.explanation}</p>
            {example.code ? <PythonCodeBlock code={example.code} ariaLabel={t.pythonExampleLabel(example.title)} /> : null}
            <dl>
              <dt>{t.run}</dt><dd><code>{example.command}</code></dd>
              <dt>{t.expected}</dt><dd><code>{example.expected_output}</code></dd>
            </dl>
            {example.trace?.length ? (
              <section className="lesson-trace" aria-label={t.traceLabel(example.title)}>
                <h4>{t.concreteTrace}</h4>
                <ol>
                  {example.trace.map((step) => (
                    <li key={step.id}>
                      <dl>
                        <dt>{t.inputState}</dt><dd>{step.input_state}</dd>
                        <dt>{t.operation}</dt><dd>{step.operation}</dd>
                        <dt>{t.outputState}</dt><dd>{step.output_state}</dd>
                        <dt>{t.why}</dt><dd>{step.explanation}</dd>
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
        <summary>{t.deepDive}</summary>
        <div className="lesson-disclosure-body">
          {outline.concepts.map((concept) => <ConceptDeepDive key={concept.id} concept={concept} t={t} />)}
        </div>
      </details>

      <details className="lesson-deep-dive lesson-diagnostic">
        <summary>{t.diagnostics}</summary>
        <div className="lesson-disclosure-body">
          {diagnosticExamples.map((example) => (
            <article key={example.id}>
              <h3>{example.title}</h3>
              <p>{example.explanation}</p>
              <h4>{t.wrongCode}</h4>
              {example.wrong_code ? <PythonCodeBlock code={example.wrong_code} ariaLabel={t.wrongCodeLabel(example.title)} /> : null}
              <p><strong>{t.symptom}</strong>{example.symptom}</p>
              <p><strong>{t.rootCause}</strong>{example.cause}</p>
              <h4>{t.fixedCode}</h4>
              {example.fix_code ? <PythonCodeBlock code={example.fix_code} ariaLabel={t.fixedCodeLabel(example.title)} /> : null}
            </article>
          ))}
        </div>
      </details>

      <section className="lesson-bridge" aria-label={t.capstoneBridgeLabel}>
        <h2>{t.capstoneBridge}</h2>
        <dl>
          <dt>{t.input}</dt><dd>{outline.capstone_bridge.input}</dd>
          <dt>{t.output}</dt><dd>{outline.capstone_bridge.output}</dd>
          <dt>{t.chapterIncrement}</dt><dd>{outline.capstone_bridge.increment}</dd>
          <dt>{t.nextChapter}</dt><dd>{outline.capstone_bridge.next}</dd>
        </dl>
        <h3>{t.chapterSummary}</h3>
        <BulletList items={outline.summary} />
      </section>
    </>
  );
}

export function CourseLesson({ content, language, onPractice }: CourseLessonProps) {
  const t = courseCopy(language);
  const tutorial = content.lesson_format === "tutorial-markdown-v1";
  return (
    <article
      className={`course-lesson${tutorial ? " tutorial-lesson" : " legacy-lesson"}`}
      aria-label={t.lessonLabel(content.title)}
    >
      {!tutorial && content.concepts?.length ? (
        <div className="concept-row" aria-label={t.chapterConcepts}>
          {content.concepts.map((concept) => <span key={concept}>{concept}</span>)}
        </div>
      ) : null}
      {!tutorial && content.lesson_outline
        ? (
            <StructuredLesson
              outline={content.lesson_outline}
              studyMinutes={content.study_minutes}
              practiceLinks={content.practice_links ?? []}
              onPractice={onPractice}
              t={t}
            />
          )
        : markdownBlocks(content.lesson, t)}
      {content.capstone_increment ? (
        <aside className="capstone-note"><strong>{t.capstoneLabel}</strong><span>{content.capstone_increment}</span></aside>
      ) : null}
      {content.sources?.length ? (
        <details className="source-list">
          <summary>{t.sourcesSummary}</summary>
          <div aria-label={t.references}>
            {content.sources.map((source) => (
              <a key={source.id} href={source.url} target="_blank" rel="noopener noreferrer">{source.title}</a>
            ))}
          </div>
        </details>
      ) : null}
    </article>
  );
}
