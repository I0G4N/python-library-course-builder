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

export type MarkdownListBlock = {
  ordered: boolean;
  start?: number;
  items: string[];
  nextIndex: number;
};

export function headingSlug(value: unknown): string;
export function extractTutorialHeadings(markdown: unknown): TutorialHeading[];
export function consumeMarkdownList(
  lines: readonly string[],
  startIndex: number,
): MarkdownListBlock | null;
export function extractLessonTerms(outline: unknown): LessonTerm[];
