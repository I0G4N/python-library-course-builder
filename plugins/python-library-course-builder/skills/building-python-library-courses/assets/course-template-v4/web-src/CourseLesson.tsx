import { Fragment, type ReactNode } from "react";
import katex from "katex";

import { PythonCodeBlock } from "@legacy/PythonCode";
import {
  courseCopy,
  type CourseCopy,
  type CourseLanguage,
} from "@legacy/courseLocale.mjs";

import {
  consumeMarkdownList,
  extractTutorialHeadings,
  normalizeLessonTerms,
  type LessonTerm,
  type TutorialHeading,
} from "./lessonGuide.mjs";

export type StudyMinutes =
  | { tier: "orientation"; min: 15; max: 30; reason?: never }
  | { tier: "standard"; min: 30; max: 45; reason?: never }
  | {
      tier: "foundation" | "extended";
      min: 45;
      max: 60;
      reason: string;
    };

export type PracticeLink = {
  kind: "knowledge-check" | "coding-question";
  item_id: string;
  title: string;
};

export type CourseContentItem = {
  id: string;
  title: string;
  lesson: string;
  lesson_format?: "tutorial-markdown-v1";
  terms?: LessonTerm[];
  sources?: Array<{ id: string; title: string; url: string }>;
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
const INLINE_TOKEN =
  /(`[^`]+`|\\\((?:(?!\\\(|\\\)|`)[\s\S])*\\\)|\[[^\]]+\]\([^)]+\)|\*\*[^*]+\*\*)/g;

type MathMarkupProps = {
  source: string;
  literal: string;
  displayMode: boolean;
};

function MathMarkup({ source, literal, displayMode }: MathMarkupProps) {
  try {
    const html = katex.renderToString(source, {
      displayMode,
      trust: false,
      throwOnError: false,
      strict: "warn",
      output: "htmlAndMathml",
      maxSize: 20,
      maxExpand: 1000,
    });
    return displayMode ? (
      <div
        className="math-render math-display"
        dangerouslySetInnerHTML={{ __html: html }}
      />
    ) : (
      <span
        className="math-render math-inline"
        dangerouslySetInnerHTML={{ __html: html }}
      />
    );
  } catch {
    return displayMode ? (
      <pre className="math-display math-error">{literal}</pre>
    ) : (
      <code className="math-inline math-error">{literal}</code>
    );
  }
}

function inlineMarkdown(value: string): ReactNode[] {
  return value
    .split(INLINE_TOKEN)
    .filter(Boolean)
    .map((part, index) => {
      if (part.startsWith("`") && part.endsWith("`")) {
        return <code key={index}>{part.slice(1, -1)}</code>;
      }
      if (part.startsWith("\\(") && part.endsWith("\\)")) {
        return (
          <MathMarkup
            key={index}
            source={part.slice(2, -2)}
            literal={part}
            displayMode={false}
          />
        );
      }
      if (part.startsWith("**") && part.endsWith("**")) {
        return <strong key={index}>{part.slice(2, -2)}</strong>;
      }
      const link = /^\[([^\]]+)\]\(([^)]+)\)$/.exec(part);
      if (link) {
        const [, label, href] = link;
        if (SAFE_FRAGMENT_LINK.test(href)) {
          return (
            <a key={index} href={href}>
              {label}
            </a>
          );
        }
        return SAFE_EXTERNAL_LINK.test(href) ? (
          <a
            key={index}
            href={href}
            target="_blank"
            rel="noopener noreferrer"
          >
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
  return line
    .trim()
    .replace(/^\|/, "")
    .replace(/\|$/, "")
    .split("|")
    .map((cell) => cell.trim());
}

function headingBlock(
  level: number,
  id: string,
  children: ReactNode[],
): ReactNode {
  if (level === 1) return <h1 id={id}>{children}</h1>;
  if (level === 2) return <h2 id={id}>{children}</h2>;
  if (level === 3) return <h3 id={id}>{children}</h3>;
  if (level === 4) return <h4 id={id}>{children}</h4>;
  if (level === 5) return <h5 id={id}>{children}</h5>;
  return <h6 id={id}>{children}</h6>;
}

type DisplayMathBlock = {
  source: string;
  literal: string;
  nextIndex: number;
};

type ListContinuationBlock = {
  markdown: string;
  nextIndex: number;
};

function startsDisplayBoundary(lines: string[], index: number): boolean {
  const line = lines[index] ?? "";
  const trimmed = line.trim();
  return (
    !trimmed ||
    /^ {0,3}\\\[/.test(line) ||
    /^(#{1,6})\s+/.test(line) ||
    /^ {0,3}```/.test(line) ||
    /^>\s?/.test(line) ||
    /^ {0,3}(?:[-+*]|\d+[.)])[ \t]+/.test(line) ||
    /^---+$/.test(trimmed) ||
    (/^\s*\|?.+\|.+\|?\s*$/.test(line) &&
      /^\s*\|?\s*:?-{3,}/.test(lines[index + 1] ?? ""))
  );
}

function consumeDisplayMath(
  lines: string[],
  startIndex: number,
): DisplayMathBlock | null {
  const opening = /^ {0,3}\\\[(.*)$/.exec(lines[startIndex]);
  if (!opening) return null;

  const firstLine = opening[1];
  const sameLineClose = firstLine.indexOf("\\]");
  if (sameLineClose >= 0) {
    if (firstLine.slice(sameLineClose + 2).trim()) return null;
    return {
      source: firstLine.slice(0, sameLineClose).trim(),
      literal: lines[startIndex].trim(),
      nextIndex: startIndex + 1,
    };
  }

  const sourceLines = [firstLine];
  for (let index = startIndex + 1; index < lines.length; index += 1) {
    const line = lines[index];
    const close = line.indexOf("\\]");
    if (close >= 0) {
      if (line.slice(close + 2).trim()) return null;
      sourceLines.push(line.slice(0, close));
      return {
        source: sourceLines.join("\n").trim(),
        literal: lines.slice(startIndex, index + 1).join("\n"),
        nextIndex: index + 1,
      };
    }
    if (startsDisplayBoundary(lines, index)) return null;
    sourceLines.push(line);
  }

  return null;
}

function consumeListContinuation(
  lines: string[],
  startIndex: number,
): ListContinuationBlock | null {
  if (startIndex >= lines.length || lines[startIndex].trim()) return null;

  let index = startIndex;
  while (index < lines.length && !lines[index].trim()) index += 1;
  if (index >= lines.length || !/^ {2}/.test(lines[index])) return null;

  const continuation: string[] = [];
  while (index < lines.length) {
    const line = lines[index];
    if (!line.trim()) {
      continuation.push("");
      index += 1;
      continue;
    }
    if (!/^ {2}/.test(line)) break;
    continuation.push(line.slice(2));
    index += 1;
  }
  while (!continuation.at(-1)?.trim()) continuation.pop();

  return continuation.length
    ? { markdown: continuation.join("\n"), nextIndex: index }
    : null;
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

    const fence = /^ {0,3}```([\w+-]*)\s*$/.exec(line);
    if (fence) {
      const language = fence[1].toLowerCase();
      const body: string[] = [];
      index += 1;
      while (index < lines.length && !/^ {0,3}```\s*$/.test(lines[index])) {
        body.push(lines[index]);
        index += 1;
      }
      if (index < lines.length) index += 1;
      const code = body.join("\n");
      blocks.push(
        language === "python" || language === "py" ? (
          <PythonCodeBlock
            key={`code-${blocks.length}`}
            code={code}
            ariaLabel={t.lessonPythonExample}
          />
        ) : (
          <pre key={`code-${blocks.length}`} className="plain-code">
            <code>{code}</code>
          </pre>
        ),
      );
      continue;
    }

    const displayMath = consumeDisplayMath(lines, index);
    if (displayMath) {
      blocks.push(
        <MathMarkup
          key={`math-${blocks.length}`}
          source={displayMath.source}
          literal={displayMath.literal}
          displayMode
        />,
      );
      index = displayMath.nextIndex;
      continue;
    }

    const heading = /^(#{1,6})\s+(.+?)\s*#*\s*$/.exec(line);
    if (heading) {
      const level = heading[1].length;
      const id = headings[headingIndex]?.id ?? `section-${headingIndex + 1}`;
      headingIndex += 1;
      blocks.push(
        <Fragment key={id}>
          {headingBlock(level, id, inlineMarkdown(heading[2]))}
        </Fragment>,
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
      blocks.push(
        <blockquote key={`quote-${blocks.length}`}>
          {inlineMarkdown(quote.join(" "))}
        </blockquote>,
      );
      continue;
    }

    if (
      /^\s*\|?.+\|.+\|?\s*$/.test(line) &&
      /^\s*\|?\s*:?-{3,}/.test(lines[index + 1] ?? "")
    ) {
      const headers = tableCells(line);
      index += 2;
      const rows: string[][] = [];
      while (
        index < lines.length &&
        /^\s*\|?.+\|.+\|?\s*$/.test(lines[index])
      ) {
        rows.push(tableCells(lines[index]));
        index += 1;
      }
      blocks.push(
        <div className="table-wrap" key={`table-${blocks.length}`}>
          <table>
            <thead>
              <tr>
                {headers.map((cell, cellIndex) => (
                  <th key={cellIndex}>{inlineMarkdown(cell)}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, rowIndex) => (
                <tr key={rowIndex}>
                  {row.map((cell, cellIndex) => (
                    <td key={cellIndex}>{inlineMarkdown(cell)}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>,
      );
      continue;
    }

    const list = consumeMarkdownList(lines, index);
    if (list) {
      const continuation = consumeListContinuation(lines, list.nextIndex);
      const items = list.items.map((item, itemIndex) => (
        <li key={itemIndex}>
          {inlineMarkdown(item)}
          {continuation && itemIndex === list.items.length - 1
            ? markdownBlocks(continuation.markdown, t)
            : null}
        </li>
      ));
      blocks.push(
        list.ordered ? (
          <ol key={`list-${blocks.length}`} start={list.start}>
            {items}
          </ol>
        ) : (
          <ul key={`list-${blocks.length}`}>{items}</ul>
        ),
      );
      index = continuation?.nextIndex ?? list.nextIndex;
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
      index < lines.length &&
      lines[index].trim() &&
      !/^(#{1,6})\s+|^ {0,3}```|^ {0,3}\\\[|^>\s?|^ {0,3}(?:[-+*]|\d+[.)])[ \t]+|^---+$/.test(
        lines[index],
      )
    ) {
      paragraph.push(lines[index].trim());
      index += 1;
    }
    blocks.push(
      <p key={`paragraph-${blocks.length}`}>
        {inlineMarkdown(paragraph.join(" "))}
      </p>,
    );
  }

  return blocks;
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
  const headings = extractTutorialHeadings(content.lesson);
  const terms = normalizeLessonTerms(content.terms);
  return (
    <nav className="chapter-guide" aria-label={copy.label}>
      <section
        className="chapter-guide-section"
        aria-labelledby="chapter-toc-title"
      >
        <h3 id="chapter-toc-title">{copy.contents}</h3>
        {headings.length ? (
          <HeadingGuide headings={headings} />
        ) : (
          <p>{copy.emptyContents}</p>
        )}
      </section>
      {terms.length ? (
        <section
          className="chapter-guide-section chapter-terms"
          aria-labelledby="chapter-terms-title"
        >
          <h3 id="chapter-terms-title">{copy.terms}</h3>
          <TermGuide terms={terms} />
        </section>
      ) : null}
    </nav>
  );
}

export function CourseLesson({
  content,
  language,
  onPractice,
}: CourseLessonProps) {
  const t = courseCopy(language);
  const practice = content.practice_links?.[0];
  return (
    <article
      className="course-lesson tutorial-lesson"
      aria-label={t.lessonLabel(content.title)}
    >
      {markdownBlocks(content.lesson, t)}
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
      {content.capstone_increment ? (
        <aside className="capstone-note">
          <strong>{t.capstoneLabel}</strong>
          <span>{content.capstone_increment}</span>
        </aside>
      ) : null}
      {content.sources?.length ? (
        <details className="source-list">
          <summary>{t.sourcesSummary}</summary>
          <div aria-label={t.references}>
            {content.sources.map((source) => (
              <a
                key={source.id}
                href={source.url}
                target="_blank"
                rel="noopener noreferrer"
              >
                {source.title}
              </a>
            ))}
          </div>
        </details>
      ) : null}
    </article>
  );
}
