import { describe, expect, it } from "vitest";

import { isTrustedAccessHost } from "./config";

describe("trusted Memos portal hosts", () => {
  it("trusts the Cloudflare-protected personal and family portals", () => {
    expect(isTrustedAccessHost("kaosgdd.net")).toBe(true);
    expect(isTrustedAccessHost("family.kaosgdd.net")).toBe(true);
  });

  it("does not trust the standalone Memos host or lookalike domains", () => {
    expect(isTrustedAccessHost("memos.kaosgdd.net")).toBe(false);
    expect(isTrustedAccessHost("family.kaosgdd.net.example.com")).toBe(false);
  });
});
