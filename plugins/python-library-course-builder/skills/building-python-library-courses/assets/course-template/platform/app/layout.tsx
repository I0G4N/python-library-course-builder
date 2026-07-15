import type { Metadata } from "next";

import "./globals.css";
import { STATIC_COURSE_LANGUAGE } from "./courseLocale.mjs";

export const metadata: Metadata = {
  title: "CourseKit",
  description: "CourseKit",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang={STATIC_COURSE_LANGUAGE} suppressHydrationWarning>
      <body>{children}</body>
    </html>
  );
}
