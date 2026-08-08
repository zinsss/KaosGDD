import { apiUrl, usesTrustedAccess } from "./config";
import type { AuthResponse, Memo, MemoListResponse, MemosUser, MemoVisibility, RefreshResponse } from "./types";

export class MemosApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code = "",
  ) {
    super(message);
  }
}

type RequestOptions = RequestInit & { retryAuth?: boolean };

export class MemosClient {
  private accessToken = "";
  private refreshPromise: Promise<void> | null = null;

  private async request<T>(path: string, options: RequestOptions = {}): Promise<T> {
    const headers = new Headers(options.headers);
    if (options.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
    if (this.accessToken && !usesTrustedAccess) headers.set("Authorization", `Bearer ${this.accessToken}`);

    const response = await fetch(apiUrl(path), {
      ...options,
      headers,
      credentials: "include",
      cache: "no-store",
    });

    if (!usesTrustedAccess && response.status === 401 && options.retryAuth !== false && !path.startsWith("/api/v1/auth/")) {
      await this.refresh();
      return this.request<T>(path, { ...options, retryAuth: false });
    }

    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      const message = typeof payload.message === "string" ? payload.message : `Memos API returned ${response.status}`;
      const code = typeof payload.error === "string" ? payload.error : "";
      throw new MemosApiError(message, response.status, code);
    }

    if (response.status === 204 || response.headers.get("Content-Length") === "0") return undefined as T;
    const text = await response.text();
    return (text ? JSON.parse(text) : undefined) as T;
  }

  async refresh(): Promise<void> {
    if (!this.refreshPromise) {
      this.refreshPromise = this.request<RefreshResponse>("/api/v1/auth/refresh", {
        method: "POST",
        body: "{}",
        retryAuth: false,
      })
        .then((response) => {
          this.accessToken = response.accessToken;
        })
        .finally(() => {
          this.refreshPromise = null;
        });
    }
    return this.refreshPromise;
  }

  async restoreSession(): Promise<MemosUser | null> {
    if (usesTrustedAccess) {
      try {
        return await this.currentUser();
      } catch (error) {
        if (error instanceof MemosApiError && error.code === "memos_relay_profile_not_configured") {
          try {
            return await this.bootstrap();
          } catch (bootstrapError) {
            if (bootstrapError instanceof MemosApiError && bootstrapError.status === 401) return null;
            throw bootstrapError;
          }
        }
        if (error instanceof MemosApiError && error.status === 401) return null;
        throw error;
      }
    }
    try {
      await this.refresh();
      return await this.currentUser();
    } catch (error) {
      this.accessToken = "";
      if (error instanceof MemosApiError && error.status === 401) return null;
      throw error;
    }
  }

  async signIn(username: string, password: string): Promise<MemosUser> {
    if (usesTrustedAccess) return this.bootstrap(username, password);
    const response = await this.request<AuthResponse>("/api/v1/auth/signin", {
      method: "POST",
      body: JSON.stringify({ passwordCredentials: { username, password } }),
      retryAuth: false,
    });
    this.accessToken = response.accessToken;
    return response.user;
  }

  async signOut(): Promise<void> {
    if (usesTrustedAccess) return;
    try {
      await this.request<void>("/api/v1/auth/signout", { method: "POST", body: "{}", retryAuth: false });
    } finally {
      this.accessToken = "";
    }
  }

  async currentUser(): Promise<MemosUser> {
    const response = await this.request<{ user: MemosUser }>("/api/v1/auth/me");
    return response.user;
  }

  private async bootstrap(username = "", password = ""): Promise<MemosUser> {
    const response = await this.request<{ user: MemosUser }>("/bootstrap", {
      method: "POST",
      body: JSON.stringify(username || password ? { username, password } : {}),
      retryAuth: false,
    });
    return response.user;
  }

  async listMemos(options: {
    creator: string;
    search?: string;
    tag?: string;
    pageToken?: string;
  }): Promise<MemoListResponse> {
    const filters = [`creator == ${JSON.stringify(options.creator)}`];
    if (options.search?.trim()) filters.push(`content.contains(${JSON.stringify(options.search.trim())})`);
    if (options.tag) filters.push(`tag in [${JSON.stringify(options.tag)}]`);
    const query = new URLSearchParams({
      pageSize: "50",
      orderBy: "pinned desc, create_time desc",
      filter: filters.join(" && "),
    });
    if (options.pageToken) query.set("pageToken", options.pageToken);
    return this.request<MemoListResponse>(`/api/v1/memos?${query.toString()}`);
  }

  async createMemo(content: string, visibility: MemoVisibility): Promise<Memo> {
    return this.request<Memo>("/api/v1/memos", {
      method: "POST",
      body: JSON.stringify({ state: "NORMAL", content, visibility }),
    });
  }

  async updateMemo(name: string, changes: Partial<Pick<Memo, "content" | "pinned" | "visibility">>): Promise<Memo> {
    const paths = Object.keys(changes);
    const id = encodeURIComponent(name.replace(/^memos\//, ""));
    return this.request<Memo>(`/api/v1/memos/${id}?updateMask=${encodeURIComponent(paths.join(","))}`, {
      method: "PATCH",
      body: JSON.stringify({ name, ...changes }),
    });
  }

  async deleteMemo(name: string): Promise<void> {
    const id = encodeURIComponent(name.replace(/^memos\//, ""));
    return this.request<void>(`/api/v1/memos/${id}`, { method: "DELETE" });
  }
}

export const memosClient = new MemosClient();
