import { afterEach, describe, expect, it, vi } from "vitest";
import { MemosClient } from "./api";

function response(payload: unknown, status = 200): Response {
  return new Response(payload === undefined ? "" : JSON.stringify(payload), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("MemosClient", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("signs in with the v0.29.1 REST password payload and uses the access token", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response({ user: { name: "users/zin", username: "zin" }, accessToken: "short-token" }))
      .mockResolvedValueOnce(response({ memos: [], nextPageToken: "" }));
    vi.stubGlobal("fetch", fetchMock);
    const client = new MemosClient();

    await client.signIn("zin", "secret");
    await client.listMemos({ creator: "users/zin", search: "backup", tag: "work" });

    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({ passwordCredentials: { username: "zin", password: "secret" } });
    const listUrl = new URL(fetchMock.mock.calls[1][0], "https://example.test");
    expect(listUrl.searchParams.get("filter")).toBe('creator == "users/zin" && content.contains("backup") && tag in ["work"]');
    expect(new Headers(fetchMock.mock.calls[1][1].headers).get("Authorization")).toBe("Bearer short-token");
  });

  it("restores a session through the HttpOnly refresh cookie", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response({ accessToken: "restored-token", expiresAt: "2026-08-08T00:00:00Z" }))
      .mockResolvedValueOnce(response({ user: { name: "users/family", username: "family" } }));
    vi.stubGlobal("fetch", fetchMock);
    const client = new MemosClient();

    await expect(client.restoreSession()).resolves.toMatchObject({ username: "family" });
    expect(fetchMock.mock.calls[0][1].credentials).toBe("include");
    expect(new Headers(fetchMock.mock.calls[1][1].headers).get("Authorization")).toBe("Bearer restored-token");
  });

  it("uses field masks for compatible memo updates", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response({ user: { name: "users/zin", username: "zin" }, accessToken: "token" }))
      .mockResolvedValueOnce(response({ name: "memos/abc", content: "changed", pinned: true }));
    vi.stubGlobal("fetch", fetchMock);
    const client = new MemosClient();
    await client.signIn("zin", "secret");

    await client.updateMemo("memos/abc", { content: "changed", pinned: true });

    const updateUrl = new URL(fetchMock.mock.calls[1][0], "https://example.test");
    expect(updateUrl.pathname).toBe("/api/v1/memos/abc");
    expect(updateUrl.searchParams.get("updateMask")).toBe("content,pinned");
  });
});
