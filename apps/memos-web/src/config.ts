export type AppMode = "personal" | "family";

export interface RuntimeConfig {
  appName: string;
  appMode: AppMode;
  memosBaseUrl: string;
  kaosPrintUrl: string;
  defaultEditorMode: "wysiwyg" | "markdown";
  allowMarkdownMode: boolean;
  theme: string;
}

declare global {
  interface Window {
    KAOS_MEMOS_CONFIG?: Partial<RuntimeConfig>;
  }
}

const browserWindow = typeof window === "undefined" ? undefined : window;
const hostIsFamily = browserWindow?.location.hostname === "family.kaosgdd.net";

export function isTrustedAccessHost(hostname: string): boolean {
  return hostname === "kaosgdd.net" || hostname === "family.kaosgdd.net";
}

export const usesTrustedAccess = Boolean(
  browserWindow && isTrustedAccessHost(browserWindow.location.hostname),
);

export const config: RuntimeConfig = {
  appName: hostIsFamily ? "가족 메모" : "Kaos Memos",
  appMode: hostIsFamily ? "family" : "personal",
  memosBaseUrl: "",
  kaosPrintUrl: "",
  defaultEditorMode: hostIsFamily ? "wysiwyg" : "markdown",
  allowMarkdownMode: !hostIsFamily,
  theme: hostIsFamily ? "family" : "nord",
  ...browserWindow?.KAOS_MEMOS_CONFIG,
};

export function apiUrl(path: string): string {
  const base = (usesTrustedAccess ? "/api/memos" : config.memosBaseUrl).replace(/\/$/, "");
  return `${base}${path}`;
}
