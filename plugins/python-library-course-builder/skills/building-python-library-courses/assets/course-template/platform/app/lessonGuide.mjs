const HEADING = /^(#{1,6})\s+(.+?)\s*#*\s*$/;
const LIST_ITEM = /^ {0,3}([-+*]|\d+[.)])[ \t]+(.*)$/;
const INLINE_MARKDOWN = /!?(?:\[([^\]]+)\]\([^)]+\)|`([^`]+)`|\*\*([^*]+)\*\*|__([^_]+)__|\*([^*]+)\*|_([^_]+)_)/g;

function headingText(value) {
  return String(value ?? "")
    .replace(INLINE_MARKDOWN, (_match, ...groups) => groups.find(Boolean) ?? "")
    .replace(/<[^>]*>/g, "")
    .replace(/\\([\\`*_[\]{}()#+.!-])/g, "$1")
    .replace(/\s+/g, " ")
    .trim();
}

export function headingSlug(value) {
  const normalized = headingText(value)
    .normalize("NFKD")
    .replace(/\p{Mark}+/gu, "")
    .toLocaleLowerCase("en")
    .replace(/[^\p{Letter}\p{Number}]+/gu, "-")
    .replace(/^-+|-+$/g, "");
  return normalized || "section";
}

export function extractTutorialHeadings(markdown) {
  const headings = [];
  const occurrences = new Map();
  let inFence = false;

  for (const line of String(markdown ?? "").replace(/\r\n/g, "\n").split("\n")) {
    if (/^```/.test(line.trim())) {
      inFence = !inFence;
      continue;
    }
    if (inFence) continue;

    const match = HEADING.exec(line);
    if (!match) continue;
    const title = headingText(match[2]);
    if (!title) continue;
    const base = `section-${headingSlug(title)}`;
    const occurrence = (occurrences.get(base) ?? 0) + 1;
    occurrences.set(base, occurrence);
    headings.push({
      id: occurrence === 1 ? base : `${base}-${occurrence}`,
      title,
      level: match[1].length,
    });
  }
  return headings;
}

function listItem(line) {
  const match = LIST_ITEM.exec(line);
  if (!match) return null;
  const ordered = /^\d/.test(match[1]);
  return {
    ordered,
    start: ordered ? Number.parseInt(match[1], 10) : undefined,
    text: match[2].trim(),
  };
}

function startsMarkdownBlock(lines, index) {
  const line = lines[index] ?? "";
  const trimmed = line.trim();
  if (
    HEADING.test(line) ||
    /^```/.test(trimmed) ||
    /^>\s?/.test(line) ||
    /^---+$/.test(trimmed)
  ) {
    return true;
  }
  return /^\s*\|?.+\|.+\|?\s*$/.test(line) &&
    /^\s*\|?\s*:?-{3,}/.test(lines[index + 1] ?? "");
}

export function consumeMarkdownList(lines, startIndex) {
  if (!Array.isArray(lines) || !Number.isInteger(startIndex)) return null;
  const first = listItem(lines[startIndex] ?? "");
  if (!first) return null;

  const items = [first.text];
  let index = startIndex + 1;
  while (index < lines.length) {
    const line = lines[index];
    if (!line.trim()) break;

    const nextItem = listItem(line);
    if (nextItem) {
      if (nextItem.ordered !== first.ordered) break;
      items.push(nextItem.text);
      index += 1;
      continue;
    }
    if (startsMarkdownBlock(lines, index)) break;

    const continuation = line.trim();
    items[items.length - 1] = `${items[items.length - 1]} ${continuation}`.trim();
    index += 1;
  }

  return {
    ordered: first.ordered,
    start: first.start,
    items,
    nextIndex: index,
  };
}

export function extractLessonTerms(outline) {
  const concepts = Array.isArray(outline?.concepts) ? outline.concepts : [];
  const seen = new Set();
  return concepts.flatMap((concept) => {
    const id = typeof concept?.id === "string" ? concept.id.trim() : "";
    const name = typeof concept?.name === "string" ? concept.name.trim() : "";
    const definition = typeof concept?.definition === "string"
      ? concept.definition.trim()
      : "";
    const key = (id || name).toLocaleLowerCase("en");
    if (!name || !definition || !key || seen.has(key)) return [];
    seen.add(key);
    return [{ id: id || headingSlug(name), name, definition }];
  });
}
