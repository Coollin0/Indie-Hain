"use client";

import { useEffect, useMemo, useState } from "react";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ||
  "https://indie-hain.corneliusgames.com";

type User = {
  id: number;
  email: string;
  role: string;
  username: string;
  avatar_url?: string;
};

type Submission = {
  id: number;
  app_slug: string;
  version: string;
  platform: string;
  channel: string;
  status: string;
  note?: string;
};

type Game = {
  id: number;
  slug: string;
  title: string;
  price: number;
  description: string;
  cover_url: string;
  sale_percent: number;
  purchase_count: number;
};

type Manifest = {
  app: string;
  version: string;
  platform: string;
  channel: string;
  total_size: number;
  files: Array<{ path: string; size: number }>;
};

const TOKEN_KEY = "indie-hain-access";
const REFRESH_KEY = "indie-hain-refresh";

async function apiFetch(
  path: string,
  init: RequestInit = {},
  tokens?: { access?: string; refresh?: string }
) {
  const headers = new Headers(init.headers || {});
  if (tokens?.access) {
    headers.set("Authorization", `Bearer ${tokens.access}`);
  }
  headers.set("Content-Type", "application/json");
  const res = await fetch(`${API_BASE}${path}`, { ...init, headers });
  return res;
}

export default function Home() {
  const [tab, setTab] = useState<"users" | "submissions" | "games">("users");
  const [accessToken, setAccessToken] = useState<string | null>(null);
  const [refreshToken, setRefreshToken] = useState<string | null>(null);
  const [me, setMe] = useState<User | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const [users, setUsers] = useState<User[]>([]);
  const [submissions, setSubmissions] = useState<Submission[]>([]);
  const [games, setGames] = useState<Game[]>([]);
  const [manifest, setManifest] = useState<Manifest | null>(null);
  const [resetPassword, setResetPassword] = useState<{
    user: User;
    password: string;
  } | null>(null);

  const isAuthed = !!accessToken && !!me;

  useEffect(() => {
    const storedAccess = localStorage.getItem(TOKEN_KEY);
    const storedRefresh = localStorage.getItem(REFRESH_KEY);
    if (storedAccess) {
      setAccessToken(storedAccess);
    }
    if (storedRefresh) {
      setRefreshToken(storedRefresh);
    }
  }, []);

  useEffect(() => {
    const init = async () => {
      if (!accessToken) return;
      setLoading(true);
      try {
        const res = await apiFetch("/api/auth/me", { method: "GET" }, { access: accessToken });
        if (res.status === 401 && refreshToken) {
          const refreshed = await apiFetch(
            "/api/auth/refresh",
            { method: "POST", body: JSON.stringify({ refresh_token: refreshToken }) },
            {}
          );
          if (!refreshed.ok) {
            throw new Error("Session abgelaufen. Bitte neu einloggen.");
          }
          const data = await refreshed.json();
          const newAccess = data.access_token;
          const newRefresh = data.refresh_token;
          localStorage.setItem(TOKEN_KEY, newAccess);
          localStorage.setItem(REFRESH_KEY, newRefresh);
          setAccessToken(newAccess);
          setRefreshToken(newRefresh);
          return;
        }
        if (!res.ok) {
          throw new Error("Login ungültig.");
        }
        const data = await res.json();
        if (data.user?.role !== "admin") {
          throw new Error("Kein Admin-Zugang.");
        }
        setMe(data.user);
      } catch (err: any) {
        setError(err.message || "Fehler beim Login.");
        setAccessToken(null);
        setRefreshToken(null);
        setMe(null);
        localStorage.removeItem(TOKEN_KEY);
        localStorage.removeItem(REFRESH_KEY);
      } finally {
        setLoading(false);
      }
    };
    init();
  }, [accessToken, refreshToken]);

  const loadData = async () => {
    if (!accessToken) return;
    setLoading(true);
    setError(null);
    try {
      const [usersRes, subsRes, gamesRes] = await Promise.all([
        apiFetch("/api/admin/users", { method: "GET" }, { access: accessToken }),
        apiFetch("/api/admin/submissions", { method: "GET" }, { access: accessToken }),
        fetch(`${API_BASE}/api/public/apps`),
      ]);

      if (!usersRes.ok) throw new Error("User-Liste konnte nicht geladen werden.");
      if (!subsRes.ok) throw new Error("Game Anfragen konnten nicht geladen werden.");
      if (!gamesRes.ok) throw new Error("Games konnten nicht geladen werden.");

      const usersData = await usersRes.json();
      const subsData = await subsRes.json();
      const gamesData = await gamesRes.json();

      setUsers(usersData.items || []);
      setSubmissions(subsData.items || []);
      setGames(gamesData || []);
    } catch (err: any) {
      setError(err.message || "Fehler beim Laden.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (isAuthed) {
      loadData();
    }
  }, [isAuthed]);

  const login = async (identity: string, password: string) => {
    setError(null);
    setLoading(true);
    try {
      const payload: any = { password };
      if (identity.includes("@")) payload.email = identity;
      else payload.username = identity;
      const res = await apiFetch("/api/auth/login", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      if (!res.ok) throw new Error("Login fehlgeschlagen.");
      const data = await res.json();
      localStorage.setItem(TOKEN_KEY, data.access_token);
      localStorage.setItem(REFRESH_KEY, data.refresh_token);
      setAccessToken(data.access_token);
      setRefreshToken(data.refresh_token);
    } catch (err: any) {
      setError(err.message || "Login fehlgeschlagen.");
    } finally {
      setLoading(false);
    }
  };

  const logout = () => {
    setAccessToken(null);
    setRefreshToken(null);
    setMe(null);
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(REFRESH_KEY);
  };

  const resetUserPassword = async (user: User) => {
    if (!accessToken) return;
    if (!confirm(`Passwort für ${user.email} wirklich zurücksetzen?`)) return;
    setLoading(true);
    try {
      const res = await apiFetch(
        `/api/admin/users/${user.id}/reset-password`,
        { method: "POST", body: JSON.stringify({}) },
        { access: accessToken }
      );
      if (!res.ok) throw new Error("Passwort-Reset fehlgeschlagen.");
      const data = await res.json();
      setResetPassword({ user, password: data.password });
    } catch (err: any) {
      setError(err.message || "Passwort-Reset fehlgeschlagen.");
    } finally {
      setLoading(false);
    }
  };

  const approveSubmission = async (submission: Submission, approve: boolean) => {
    if (!accessToken) return;
    setLoading(true);
    try {
      const endpoint = approve ? "approve" : "reject";
      const res = await apiFetch(
        `/api/admin/submissions/${submission.id}/${endpoint}`,
        { method: "POST" },
        { access: accessToken }
      );
      if (!res.ok) throw new Error("Aktion fehlgeschlagen.");
      await loadData();
    } catch (err: any) {
      setError(err.message || "Aktion fehlgeschlagen.");
    } finally {
      setLoading(false);
    }
  };

  const loadManifest = async (submission: Submission) => {
    if (!accessToken) return;
    setLoading(true);
    try {
      const res = await apiFetch(
        `/api/admin/submissions/${submission.id}/manifest`,
        { method: "GET" },
        { access: accessToken }
      );
      if (!res.ok) throw new Error("Manifest konnte nicht geladen werden.");
      const data = await res.json();
      setManifest(data);
    } catch (err: any) {
      setError(err.message || "Manifest konnte nicht geladen werden.");
    } finally {
      setLoading(false);
    }
  };

  const stats = useMemo(() => {
    const pending = submissions.filter((s) => s.status === "pending").length;
    return [
      { label: "Users", value: users.length },
      { label: "Anfragen", value: pending },
      { label: "Games", value: games.length },
    ];
  }, [users, submissions, games]);

  return (
    <div className="min-h-screen px-6 py-10">
      <div className="mx-auto flex w-full max-w-6xl flex-col gap-8">
        <header className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div className="space-y-2">
            <p className="text-xs uppercase tracking-[0.3em] text-[var(--muted)]">
              Indie-Hain Admin
            </p>
            <h1 className="text-3xl font-semibold text-[var(--ink)]">
              Dashboard
            </h1>
          </div>
          {isAuthed && me ? (
            <div className="flex flex-wrap items-center gap-3">
              <span className="rounded-full border border-[var(--stroke)] px-4 py-2 text-sm text-[var(--muted)]">
                Eingeloggt als {me.email}
              </span>
              <button
                onClick={logout}
                className="rounded-full border border-[var(--stroke)] px-5 py-2 text-sm text-[var(--ink)] transition hover:border-[var(--accent)]"
              >
                Logout
              </button>
            </div>
          ) : null}
        </header>

        {!isAuthed ? (
          <section className="glass mx-auto w-full max-w-xl rounded-3xl p-8">
            <h2 className="text-xl font-semibold">Admin Login</h2>
            <p className="mt-2 text-sm text-[var(--muted)]">
              Verwende deinen Admin-Account von Indie-Hain.
            </p>
            <LoginForm onSubmit={login} loading={loading} error={error} />
          </section>
        ) : (
          <>
            <section className="grid gap-4 md:grid-cols-3">
              {stats.map((stat) => (
                <div
                  key={stat.label}
                  className="card rounded-2xl p-5 text-sm text-[var(--muted)]"
                >
                  <p className="uppercase tracking-[0.2em]">{stat.label}</p>
                  <p className="mt-2 text-3xl font-semibold text-[var(--ink)]">
                    {stat.value}
                  </p>
                </div>
              ))}
            </section>

            <section className="card rounded-3xl p-6">
              <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[var(--stroke)] pb-4">
                <div className="flex items-center gap-2">
                  {(["users", "submissions", "games"] as const).map((key) => (
                    <button
                      key={key}
                      onClick={() => setTab(key)}
                      className={`rounded-full px-4 py-2 text-sm transition ${
                        tab === key
                          ? "bg-[var(--accent)] text-black"
                          : "border border-[var(--stroke)] text-[var(--muted)] hover:border-[var(--accent)]"
                      }`}
                    >
                      {key === "users"
                        ? "User"
                        : key === "submissions"
                        ? "Game Anfragen"
                        : "Games"}
                    </button>
                  ))}
                </div>
                <button
                  onClick={loadData}
                  className="rounded-full border border-[var(--stroke)] px-4 py-2 text-sm text-[var(--muted)] hover:border-[var(--accent)]"
                >
                  {loading ? "Lädt..." : "Aktualisieren"}
                </button>
              </div>

              {error ? (
                <div className="mt-4 rounded-2xl border border-[var(--danger)]/40 bg-[rgba(255,107,107,0.1)] px-4 py-3 text-sm text-[var(--danger)]">
                  {error}
                </div>
              ) : null}

              {tab === "users" ? (
                <UsersTable users={users} onReset={resetUserPassword} />
              ) : null}

              {tab === "submissions" ? (
                <SubmissionsTable
                  submissions={submissions}
                  onApprove={(s) => approveSubmission(s, true)}
                  onReject={(s) => approveSubmission(s, false)}
                  onManifest={loadManifest}
                />
              ) : null}

              {tab === "games" ? <GamesTable games={games} /> : null}
            </section>
          </>
        )}
      </div>

      {manifest ? (
        <Modal
          title="Manifest"
          onClose={() => setManifest(null)}
          content={
            <div className="space-y-2 text-sm text-[var(--muted)]">
              <p>
                <span className="text-[var(--ink)]">App:</span> {manifest.app}
              </p>
              <p>
                <span className="text-[var(--ink)]">Version:</span>{" "}
                {manifest.version}
              </p>
              <p>
                <span className="text-[var(--ink)]">Platform:</span>{" "}
                {manifest.platform} ({manifest.channel})
              </p>
              <p>
                <span className="text-[var(--ink)]">Files:</span>{" "}
                {manifest.files?.length || 0}
              </p>
              <p>
                <span className="text-[var(--ink)]">Total Size:</span>{" "}
                {formatBytes(manifest.total_size)}
              </p>
            </div>
          }
        />
      ) : null}

      {resetPassword ? (
        <Modal
          title="Passwort zurückgesetzt"
          onClose={() => setResetPassword(null)}
          content={
            <div className="space-y-3 text-sm text-[var(--muted)]">
              <p>
                Neues Passwort für{" "}
                <span className="text-[var(--ink)]">
                  {resetPassword.user.email}
                </span>
                :
              </p>
              <div className="flex items-center justify-between gap-3 rounded-xl border border-[var(--stroke)] bg-[var(--bg-soft)] px-4 py-3 font-mono text-[var(--ink)]">
                <span>{resetPassword.password}</span>
                <button
                  onClick={() => navigator.clipboard.writeText(resetPassword.password)}
                  className="text-xs uppercase tracking-[0.2em] text-[var(--accent)]"
                >
                  Copy
                </button>
              </div>
            </div>
          }
        />
      ) : null}
    </div>
  );
}

function LoginForm({
  onSubmit,
  loading,
  error,
}: {
  onSubmit: (identity: string, password: string) => void;
  loading: boolean;
  error: string | null;
}) {
  const [identity, setIdentity] = useState("");
  const [password, setPassword] = useState("");

  return (
    <form
      className="mt-6 space-y-4"
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit(identity, password);
      }}
    >
      <div className="space-y-2">
        <label className="text-xs uppercase tracking-[0.2em] text-[var(--muted)]">
          Benutzername / E-Mail
        </label>
        <input
          value={identity}
          onChange={(e) => setIdentity(e.target.value)}
          className="w-full rounded-2xl border border-[var(--stroke)] bg-[var(--bg-soft)] px-4 py-3 text-sm text-[var(--ink)] outline-none focus:border-[var(--accent)]"
          placeholder="admin@indie-hain"
        />
      </div>
      <div className="space-y-2">
        <label className="text-xs uppercase tracking-[0.2em] text-[var(--muted)]">
          Passwort
        </label>
        <input
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="w-full rounded-2xl border border-[var(--stroke)] bg-[var(--bg-soft)] px-4 py-3 text-sm text-[var(--ink)] outline-none focus:border-[var(--accent)]"
          placeholder="••••••••"
        />
      </div>
      {error ? <p className="text-sm text-[var(--danger)]">{error}</p> : null}
      <button
        type="submit"
        disabled={loading}
        className="w-full rounded-2xl bg-[var(--accent)] py-3 text-sm font-semibold text-black transition hover:opacity-90 disabled:opacity-50"
      >
        {loading ? "Login..." : "Login"}
      </button>
    </form>
  );
}

function UsersTable({
  users,
  onReset,
}: {
  users: User[];
  onReset: (user: User) => void;
}) {
  return (
    <div className="mt-6 overflow-x-auto">
      <table className="w-full text-left text-sm">
        <thead className="text-xs uppercase tracking-[0.2em] text-[var(--muted)]">
          <tr>
            <th className="pb-3">ID</th>
            <th className="pb-3">E-Mail</th>
            <th className="pb-3">Username</th>
            <th className="pb-3">Rolle</th>
            <th className="pb-3">Aktion</th>
          </tr>
        </thead>
        <tbody className="text-[var(--ink)]">
          {users.map((user) => (
            <tr key={user.id} className="border-t border-[var(--stroke)]">
              <td className="py-3">{user.id}</td>
              <td className="py-3">{user.email}</td>
              <td className="py-3">{user.username || "-"}</td>
              <td className="py-3 capitalize">{user.role}</td>
              <td className="py-3">
                <button
                  onClick={() => onReset(user)}
                  className="rounded-full border border-[var(--stroke)] px-3 py-1 text-xs text-[var(--muted)] hover:border-[var(--accent)]"
                >
                  Passwort Reset
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function SubmissionsTable({
  submissions,
  onApprove,
  onReject,
  onManifest,
}: {
  submissions: Submission[];
  onApprove: (submission: Submission) => void;
  onReject: (submission: Submission) => void;
  onManifest: (submission: Submission) => void;
}) {
  if (!submissions.length) {
    return <p className="mt-6 text-sm text-[var(--muted)]">Keine Anfragen.</p>;
  }
  return (
    <div className="mt-6 grid gap-4">
      {submissions.map((submission) => (
        <div
          key={submission.id}
          className="rounded-2xl border border-[var(--stroke)] bg-[var(--bg-soft)] p-4"
        >
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="text-sm font-semibold text-[var(--ink)]">
                {submission.app_slug}
              </p>
              <p className="text-xs text-[var(--muted)]">
                {submission.version} · {submission.platform} ·{" "}
                {submission.channel}
              </p>
            </div>
            <span
              className={`rounded-full px-3 py-1 text-xs uppercase tracking-[0.2em] ${
                submission.status === "pending"
                  ? "bg-[rgba(128,240,184,0.15)] text-[var(--accent)]"
                  : "bg-[rgba(90,212,255,0.15)] text-[var(--accent-2)]"
              }`}
            >
              {submission.status}
            </span>
          </div>
          <div className="mt-4 flex flex-wrap gap-2">
            <button
              onClick={() => onManifest(submission)}
              className="rounded-full border border-[var(--stroke)] px-3 py-1 text-xs text-[var(--muted)] hover:border-[var(--accent)]"
            >
              Manifest
            </button>
            <button
              onClick={() => onApprove(submission)}
              className="rounded-full bg-[var(--accent)] px-3 py-1 text-xs font-semibold text-black"
            >
              Approve
            </button>
            <button
              onClick={() => onReject(submission)}
              className="rounded-full border border-[var(--danger)]/50 px-3 py-1 text-xs text-[var(--danger)]"
            >
              Reject
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}

function GamesTable({ games }: { games: Game[] }) {
  if (!games.length) {
    return <p className="mt-6 text-sm text-[var(--muted)]">Keine Games.</p>;
  }
  return (
    <div className="mt-6 grid gap-4 md:grid-cols-2">
      {games.map((game) => (
        <div
          key={game.id}
          className="rounded-2xl border border-[var(--stroke)] bg-[var(--bg-soft)] p-4"
        >
          <p className="text-sm font-semibold text-[var(--ink)]">{game.title}</p>
          <p className="mt-1 text-xs text-[var(--muted)]">{game.slug}</p>
          <p className="mt-3 text-sm text-[var(--muted)]">
            {game.description || "Keine Beschreibung."}
          </p>
          <div className="mt-4 flex items-center justify-between text-xs text-[var(--muted)]">
            <span>{game.price.toFixed(2)} €</span>
            <span>{game.purchase_count} Käufe</span>
          </div>
        </div>
      ))}
    </div>
  );
}

function Modal({
  title,
  content,
  onClose,
}: {
  title: string;
  content: React.ReactNode;
  onClose: () => void;
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 px-4">
      <div className="glass w-full max-w-md rounded-3xl p-6">
        <div className="flex items-center justify-between">
          <h3 className="text-lg font-semibold">{title}</h3>
          <button
            onClick={onClose}
            className="rounded-full border border-[var(--stroke)] px-3 py-1 text-xs text-[var(--muted)]"
          >
            Schließen
          </button>
        </div>
        <div className="mt-4">{content}</div>
      </div>
    </div>
  );
}

function formatBytes(bytes?: number) {
  if (!bytes) return "0 B";
  const sizes = ["B", "KB", "MB", "GB"];
  const i = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), sizes.length - 1);
  return `${(bytes / Math.pow(1024, i)).toFixed(1)} ${sizes[i]}`;
}
