import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

import react from "@vitejs/plugin-react";
import { defineConfig, type Plugin } from "vite";

const webRoot = dirname(fileURLToPath(import.meta.url));
const legacyAppRoot = resolve(webRoot, "../../course-template/platform/app");
const v4CourseLesson = resolve(webRoot, "CourseLesson.tsx");
const staticRoot = resolve(webRoot, "../coursekit_runtime/static");

function cleanId(id: string): string {
  return id.split("?", 1)[0];
}

function sameOriginCourseKit(): Plugin {
  const courseKitApp = resolve(legacyAppRoot, "CourseKitApp.tsx");
  const knowledgeCheck = resolve(legacyAppRoot, "KnowledgeCheck.tsx");
  const courseLocale = resolve(legacyAppRoot, "courseLocale.mjs");
  const v4CourseLocale = resolve(webRoot, "courseLocaleV4.mjs");
  const runnerDeclaration =
    'const RUNNER_URL = "http://127.0.0.1:8765";';

  return {
    name: "coursekit-v4-same-origin",
    enforce: "pre",
    resolveId(source, importer) {
      if (
        source === "./CourseLesson" &&
        importer &&
        cleanId(importer) === courseKitApp
      ) {
        return v4CourseLesson;
      }
      if (
        source === "./courseLocale.mjs" &&
        importer &&
        dirname(cleanId(importer)) === legacyAppRoot
      ) {
        return v4CourseLocale;
      }
      return null;
    },
    transform(code, id) {
      const sourcePath = cleanId(id);
      if (sourcePath === courseKitApp || sourcePath === knowledgeCheck) {
        if (!code.includes(runnerDeclaration)) {
          throw new Error(`CourseKit same-origin marker is missing in ${sourcePath}`);
        }
        return code.replace(runnerDeclaration, 'const RUNNER_URL = "";');
      }
      if (sourcePath === courseLocale) {
        const generatedLanguage =
          'const GENERATED_COURSE_LANGUAGE = "__COURSEKIT_LANGUAGE__";';
        if (!code.includes(generatedLanguage)) {
          throw new Error("CourseKit runtime-language marker is missing");
        }
        return code
          .replace(
            generatedLanguage,
            [
              "const GENERATED_COURSE_LANGUAGE =",
              '  typeof document === "undefined"',
              '    ? "zh-CN"',
              "    : document.documentElement.lang;",
            ].join("\n"),
          )
          .replaceAll("npm run learn", "uv run course");
      }
      return null;
    },
  };
}

export default defineConfig({
  root: webRoot,
  base: "/",
  plugins: [sameOriginCourseKit(), react()],
  resolve: {
    alias: {
      "@legacy": legacyAppRoot,
      react: resolve(webRoot, "node_modules/react"),
      "react-dom": resolve(webRoot, "node_modules/react-dom"),
      "@codemirror": resolve(webRoot, "node_modules/@codemirror"),
      "@lezer": resolve(webRoot, "node_modules/@lezer"),
    },
  },
  server: {
    fs: {
      allow: [webRoot, legacyAppRoot],
    },
  },
  build: {
    outDir: staticRoot,
    emptyOutDir: true,
    assetsDir: "assets",
    sourcemap: false,
  },
});
