export type MemoVisibility = "PRIVATE" | "PROTECTED" | "PUBLIC";

export interface MemosUser {
  name: string;
  username: string;
  displayName?: string;
  role?: string;
}

export interface Memo {
  name: string;
  state: "NORMAL" | "ARCHIVED" | "STATE_UNSPECIFIED";
  creator: string;
  createTime: string;
  updateTime: string;
  content: string;
  visibility: MemoVisibility;
  tags?: string[];
  pinned: boolean;
  snippet?: string;
}

export interface MemoListResponse {
  memos: Memo[];
  nextPageToken?: string;
}

export interface AuthResponse {
  user: MemosUser;
  accessToken: string;
  accessTokenExpiresAt: string;
}

export interface RefreshResponse {
  accessToken: string;
  expiresAt: string;
}
