import { describe, expect, it } from "vitest";
import { contentWithoutTagOnlyLines } from "./content";

describe("contentWithoutTagOnlyLines", () => {
  it("removes a line containing only extracted tags", () => {
    expect(contentWithoutTagOnlyLines("Server notes\n\n#server, #rustdesk", ["server", "rustdesk"]))
      .toBe("Server notes\n");
  });

  it("keeps tags used as part of normal prose", () => {
    expect(contentWithoutTagOnlyLines("Use #server for infrastructure notes.", ["server"]))
      .toBe("Use #server for infrastructure notes.");
  });

  it("supports hierarchical and international tags", () => {
    expect(contentWithoutTagOnlyLines("#work/서버 #가족", ["work/서버", "가족"]))
      .toBe("");
  });
});
