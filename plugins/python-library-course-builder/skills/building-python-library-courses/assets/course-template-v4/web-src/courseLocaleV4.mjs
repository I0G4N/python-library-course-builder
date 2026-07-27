import {
  resolveCourseLanguage as resolveLegacyCourseLanguage,
} from "../../course-template/platform/app/courseLocale.mjs";

export {
  COURSE_COPY,
  STATIC_COURSE_LANGUAGE,
  SUPPORTED_COURSE_LANGUAGES,
  courseCopy,
} from "../../course-template/platform/app/courseLocale.mjs";

export function resolveCourseLanguage(schemaVersion, language) {
  if (schemaVersion !== 4) {
    return resolveLegacyCourseLanguage(schemaVersion, language);
  }
  if (language === "zh-CN" || language === "en") {
    return language;
  }
  throw new Error(
    language == null || language === ""
      ? "schema v4 manifest.language is required"
      : `schema v4 manifest.language is unsupported: ${language}`,
  );
}
