import { createRoot } from "react-dom/client";

import { CourseKitApp } from "@legacy/CourseKitApp";
import "@legacy/globals.css";
import "katex/dist/katex.min.css";
import "./v4.css";

const root = document.getElementById("root");
if (!root) {
  throw new Error("CourseKit Web root is missing");
}

createRoot(root).render(<CourseKitApp />);
