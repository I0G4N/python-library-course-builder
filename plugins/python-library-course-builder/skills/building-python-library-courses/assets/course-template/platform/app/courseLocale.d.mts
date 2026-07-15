/* eslint-disable @typescript-eslint/no-explicit-any */

export type CourseLanguage = "zh-CN" | "en";

export type CourseCopy = {
  [key: string]: any;
  runnerTimeout: string;
  unknownError: string;
  runnerRequestFailed: (detail: string) => string;
  runnerRequestStatus: (status: number, statusText: string) => string;
  studyMinutes: (min: number, max: number) => string;
  lockedLab: (labId: string) => string;
  lockedLabTitle: (labId: string) => string;
  completeSymbol: (symbol: string) => string;
  points: (value: number) => string;
  codeEditorLabel: (title: string) => string;
  knowledgeCompleted: (mastered: number, total: number) => string;
  knowledgeMastered: (mastered: number, total: number) => string;
  lessonLabel: (title: string) => string;
  inputOutputContract: (name: string) => string;
  pythonExampleLabel: (title: string) => string;
  traceLabel: (title: string) => string;
  wrongCodeLabel: (title: string) => string;
  fixedCodeLabel: (title: string) => string;
};

export const SUPPORTED_COURSE_LANGUAGES: readonly CourseLanguage[];
export const STATIC_COURSE_LANGUAGE: CourseLanguage;
export const COURSE_COPY: Readonly<Record<CourseLanguage, CourseCopy>>;
export function resolveCourseLanguage(
  schemaVersion: number | undefined,
  language: string | undefined,
): CourseLanguage;
export function courseCopy(language: CourseLanguage): CourseCopy;
