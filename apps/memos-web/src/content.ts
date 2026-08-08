function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

export function contentWithoutTagOnlyLines(content: string, tags: string[]): string {
  if (!tags.length) return content;

  const alternatives = [...tags]
    .sort((left, right) => right.length - left.length)
    .map(escapeRegExp)
    .join("|");
  const tagOnlyLine = new RegExp(`^[\\s,;]*(?:#(?:${alternatives})[\\s,;]*)+$`, "u");

  return content
    .split("\n")
    .filter((line) => !tagOnlyLine.test(line))
    .join("\n");
}
