import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { Edit3, LogOut, Pin, PinOff, Plus, Search, Trash2, X } from "lucide-react";
import ReactMarkdown from "react-markdown";
import rehypeSanitize from "rehype-sanitize";
import remarkGfm from "remark-gfm";
import { memosClient } from "./api";
import { config } from "./config";
import { t } from "./i18n";
import type { Memo, MemosUser, MemoVisibility } from "./types";

interface EditorDraft {
  memo?: Memo;
  content: string;
  visibility: MemoVisibility;
}

function formatTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return new Intl.DateTimeFormat(config.appMode === "family" ? "ko-KR" : "en-CA", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

function Login({ onSignedIn }: { onSignedIn: (user: MemosUser) => void }) {
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    setBusy(true);
    setError("");
    try {
      onSignedIn(await memosClient.signIn(String(data.get("username") || ""), String(data.get("password") || "")));
    } catch {
      setError(t.loginFailed);
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="loginPage">
      <form className="loginPanel" onSubmit={submit}>
        <p className="eyebrow">{config.appMode === "family" ? "가족" : "KAOSGDD"}</p>
        <h1>{config.appName}</h1>
        <label>
          <span>{t.username}</span>
          <input name="username" autoComplete="username" required />
        </label>
        <label>
          <span>{t.password}</span>
          <input name="password" type="password" autoComplete="current-password" required />
        </label>
        {error && <p className="errorText">{error}</p>}
        <button className="primaryButton" type="submit" disabled={busy}>{t.signIn}</button>
      </form>
    </main>
  );
}

function MemoEditor({ draft, onCancel, onSaved }: {
  draft: EditorDraft;
  onCancel: () => void;
  onSaved: (memo: Memo) => void;
}) {
  const [content, setContent] = useState(draft.content);
  const [visibility, setVisibility] = useState(draft.visibility);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!content.trim()) return;
    setBusy(true);
    setError("");
    try {
      const memo = draft.memo
        ? await memosClient.updateMemo(draft.memo.name, { content, visibility })
        : await memosClient.createMemo(content, visibility);
      onSaved(memo);
    } catch {
      setError(t.saveFailed);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="editorPanel" onSubmit={submit}>
      <div className="editorHeader">
        <h2>{draft.memo ? t.edit : t.newMemo}</h2>
        <button className="iconButton" type="button" onClick={onCancel} title={t.cancel}><X /></button>
      </div>
      <label className="editorContent">
        <span>{t.content}</span>
        <textarea value={content} onChange={(event) => setContent(event.target.value)} autoFocus />
      </label>
      <div className="editorFooter">
        <label>
          <span>{t.visibility}</span>
          <select value={visibility} onChange={(event) => setVisibility(event.target.value as MemoVisibility)}>
            <option value="PRIVATE">{t.private}</option>
            <option value="PROTECTED">{t.protected}</option>
            <option value="PUBLIC">{t.public}</option>
          </select>
        </label>
        <button className="primaryButton" type="submit" disabled={busy || !content.trim()}>{t.save}</button>
      </div>
      {error && <p className="errorText">{error}</p>}
    </form>
  );
}

function MemoCard({ memo, onEdit, onDelete, onPin, onTag }: {
  memo: Memo;
  onEdit: () => void;
  onDelete: () => void;
  onPin: () => void;
  onTag: (tag: string) => void;
}) {
  return (
    <article className="memoCard">
      <div className="memoContent">
        <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeSanitize]} components={{
          a: ({ node: _node, ...props }) => <a {...props} target="_blank" rel="noreferrer" />,
        }}>{memo.content}</ReactMarkdown>
      </div>
      {memo.tags.length > 0 && (
        <div className="tagRow">
          {memo.tags.map((tag) => <button type="button" key={tag} onClick={() => onTag(tag)}>#{tag}</button>)}
        </div>
      )}
      <footer className="memoFooter">
        <time dateTime={memo.updateTime || memo.createTime}>{formatTime(memo.updateTime || memo.createTime)}</time>
        <div className="memoActions">
          <button type="button" onClick={onEdit} title={t.edit}><Edit3 /><span>{t.edit}</span></button>
          <button type="button" onClick={onPin} title={memo.pinned ? t.unpin : t.pin}>
            {memo.pinned ? <PinOff /> : <Pin />}<span>{memo.pinned ? t.unpin : t.pin}</span>
          </button>
          <button className="dangerAction" type="button" onClick={onDelete} title={t.delete}><Trash2 /><span>{t.delete}</span></button>
        </div>
      </footer>
    </article>
  );
}

function MemoApp({ user, onSignOut }: { user: MemosUser; onSignOut: () => void }) {
  const [memos, setMemos] = useState<Memo[]>([]);
  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");
  const [tag, setTag] = useState("");
  const [nextPageToken, setNextPageToken] = useState("");
  const [editor, setEditor] = useState<EditorDraft | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async (append = false) => {
    setLoading(true);
    setError("");
    try {
      const response = await memosClient.listMemos({
        creator: user.name,
        search,
        tag,
        pageToken: append ? nextPageToken : "",
      });
      setMemos((current) => append ? [...current, ...response.memos] : response.memos);
      setNextPageToken(response.nextPageToken || "");
    } catch {
      setError(t.loadFailed);
    } finally {
      setLoading(false);
    }
  }, [nextPageToken, search, tag, user.name]);

  useEffect(() => { void load(false); }, [search, tag, user.name]);

  const tags = useMemo(() => Array.from(new Set(memos.flatMap((memo) => memo.tags))).sort(), [memos]);

  async function togglePin(memo: Memo) {
    const updated = await memosClient.updateMemo(memo.name, { pinned: !memo.pinned });
    setMemos((items) => items.map((item) => item.name === memo.name ? updated : item));
  }

  async function deleteMemo(memo: Memo) {
    if (!window.confirm(t.deleteConfirm)) return;
    await memosClient.deleteMemo(memo.name);
    setMemos((items) => items.filter((item) => item.name !== memo.name));
  }

  function savedMemo(memo: Memo) {
    setEditor(null);
    setMemos((items) => {
      const exists = items.some((item) => item.name === memo.name);
      return exists ? items.map((item) => item.name === memo.name ? memo : item) : [memo, ...items];
    });
  }

  return (
    <div className="memoApp">
      <header className="appHeader">
        <div>
          <p className="eyebrow">{config.appMode === "family" ? "가족" : "KAOSGDD"}</p>
          <h1>{config.appName}</h1>
        </div>
        <div className="headerActions">
          <span>{user.displayName || user.username}</span>
          <button className="iconButton" type="button" onClick={onSignOut} title={t.signOut}><LogOut /></button>
        </div>
      </header>

      <main className="appBody">
        <section className="controlBar">
          <form className="searchBox" onSubmit={(event) => { event.preventDefault(); setSearch(searchInput.trim()); }}>
            <Search aria-hidden="true" />
            <input value={searchInput} onChange={(event) => setSearchInput(event.target.value)} placeholder={t.search} />
            {searchInput && <button className="iconButton" type="button" onClick={() => { setSearchInput(""); setSearch(""); }}><X /></button>}
          </form>
          <button className="primaryButton addButton" type="button" onClick={() => setEditor({ content: "", visibility: "PRIVATE" })}>
            <Plus /> <span>{t.newMemo}</span>
          </button>
        </section>

        <nav className="tagFilters" aria-label={t.allTags}>
          <button className={!tag ? "active" : ""} type="button" onClick={() => setTag("")}>{t.allTags}</button>
          {tags.map((item) => <button className={tag === item ? "active" : ""} type="button" key={item} onClick={() => setTag(item)}>#{item}</button>)}
        </nav>

        {editor && <MemoEditor key={editor.memo?.name || "new"} draft={editor} onCancel={() => setEditor(null)} onSaved={savedMemo} />}
        {error && <p className="errorBanner">{error}</p>}

        <section className="memoFeed" aria-live="polite">
          {!loading && memos.length === 0 && <p className="emptyState">{t.empty}</p>}
          {memos.map((memo) => (
            <MemoCard
              key={memo.name}
              memo={memo}
              onEdit={() => setEditor({ memo, content: memo.content, visibility: memo.visibility })}
              onDelete={() => void deleteMemo(memo)}
              onPin={() => void togglePin(memo)}
              onTag={setTag}
            />
          ))}
          {nextPageToken && <button className="loadMore" type="button" disabled={loading} onClick={() => void load(true)}>{t.loadMore}</button>}
        </section>
      </main>
    </div>
  );
}

export default function App() {
  const [user, setUser] = useState<MemosUser | null>(null);
  const [initializing, setInitializing] = useState(true);

  useEffect(() => {
    document.documentElement.dataset.theme = config.theme;
    document.documentElement.lang = config.appMode === "family" ? "ko" : "en";
    document.title = config.appName;
    memosClient.restoreSession().then(setUser).finally(() => setInitializing(false));
  }, []);

  if (initializing) return <div className="loadingState" aria-label="Loading" />;
  if (!user) return <Login onSignedIn={setUser} />;
  return <MemoApp user={user} onSignOut={() => void memosClient.signOut().finally(() => setUser(null))} />;
}
