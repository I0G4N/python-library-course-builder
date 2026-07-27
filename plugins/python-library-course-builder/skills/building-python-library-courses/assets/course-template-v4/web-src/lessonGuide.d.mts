export type TutorialHeading = {
  id: string;
  title: string;
  level: number;
};

export type LessonTerm = {
  id: string;
  name: string;
  definition: string;
};

export type MarkdownList = {
  ordered: boolean;
  start?: number;
  items: string[];
  nextIndex: number;
};

export function headingSlug(value: unknown): string;
export function extractTutorialHeadings(markdown: unknown): TutorialHeading[];
export function consumeMarkdownList(
  lines: string[],
  startIndex: number,
): MarkdownList | null;
export function normalizeLessonTerms(terms: unknown): LessonTerm[];
