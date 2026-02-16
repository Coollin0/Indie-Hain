"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ||
  "https://indie-hain.corneliusgames.com";

type User = {
  id: number;
  email: string;
  role: string;
  username: string;
  avatar_url?: string;
  force_password_reset?: number;
};

type Submission = {
  id: number;
  app_slug: string;
  version: string;
  platform: string;
  channel: string;
  status: string;
  note?: string;
  created_at?: string;
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

type SubmissionFile = {
  path: string;
  size: number;
  sha256?: string;
  chunks?: Array<{ sha256: string; size?: number }>;
};

type SubmissionFilesResponse = {
  files: SubmissionFile[];
  app?: string;
  version?: string;
};

type VerifyBatchResult = {
  path: string;
  chunk_ok?: boolean;
  file_ok?: boolean;
  expected?: string;
  error?: string;
};

type VerifyBatchResponse = {
  results: VerifyBatchResult[];
  ok_count?: number;
  total?: number;
};

type Overview = {
  users: { total: number; admins: number; devs: number; users: number };
  submissions: { total: number; pending: number; approved: number; rejected: number };
  apps: { total: number; approved: number; pending: number };
  purchases: {
    total: number;
    revenue_total: number;
    count_30d: number;
    revenue_30d: number;
  };
  dev_upgrade_payments?: {
    total: number;
    open: number;
    consumed: number;
    amount_total: number;
    amount_open: number;
    amount_consumed: number;
    provider_counts?: Record<string, number>;
  };
  last_activity: {
    user?: string | null;
    submission?: string | null;
    purchase?: string | null;
    dev_upgrade_payment?: string | null;
  };
  since_30d: string;
};

type DevUpgradePayment = {
  id: number;
  user_id: number;
  user_email?: string;
  user_username?: string;
  user_role?: string;
  amount: number;
  currency: string;
  provider: string;
  payment_ref?: string;
  note?: string;
  created_at?: string;
  paid_at?: string;
  consumed_at?: string | null;
  consumed_by_user_id?: number | null;
  is_consumed?: boolean;
};

const TOKEN_KEY = "indie-hain-access";
const REFRESH_KEY = "indie-hain-refresh";

async function apiFetch(
  path: string,
  init: RequestInit = {},
  tokens?: { access?: string; refresh?: string },
  allowRefresh = true
) {
  const headers = new Headers(init.headers || {});
  const access =
    tokens?.access || (typeof window !== "undefined" ? sessionStorage.getItem(TOKEN_KEY) : null);
  if (access) {
    headers.set("Authorization", `Bearer ${access}`);
  }
  if (!headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  let res = await fetch(`${API_BASE}${path}`, { ...init, headers });
  if (res.status === 401 && allowRefresh) {
    const refresh =
      tokens?.refresh || (typeof window !== "undefined" ? sessionStorage.getItem(REFRESH_KEY) : null);
    if (refresh) {
      const refreshed = await fetch(`${API_BASE}/api/auth/refresh`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: refresh }),
      });
      if (refreshed.ok) {
        const data = await refreshed.json();
        const newAccess = data.access_token;
        const newRefresh = data.refresh_token;
        if (typeof window !== "undefined") {
          sessionStorage.setItem(TOKEN_KEY, newAccess);
          sessionStorage.setItem(REFRESH_KEY, newRefresh);
        }
        headers.set("Authorization", `Bearer ${newAccess}`);
        res = await fetch(`${API_BASE}${path}`, { ...init, headers });
      }
    }
  }
  return res;
}

export default function Home() {
  const [tab, setTab] = useState<"users" | "submissions" | "games" | "dev_upgrades">("users");
  const [accessToken, setAccessToken] = useState<string | null>(null);
  const [refreshToken, setRefreshToken] = useState<string | null>(null);
  const [me, setMe] = useState<User | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [lastSync, setLastSync] = useState<string | null>(null);
  const [overview, setOverview] = useState<Overview | null>(null);
  const [overviewSync, setOverviewSync] = useState<string | null>(null);

  const [users, setUsers] = useState<User[]>([]);
  const [submissions, setSubmissions] = useState<Submission[]>([]);
  const [games, setGames] = useState<Game[]>([]);
  const [devUpgrades, setDevUpgrades] = useState<DevUpgradePayment[]>([]);
  const [manifest, setManifest] = useState<Manifest | null>(null);
  const [filesPanel, setFilesPanel] = useState<{
    submission: Submission;
    info: SubmissionFilesResponse;
  } | null>(null);
  const [fileQuery, setFileQuery] = useState("");
  const [fileVerify, setFileVerify] = useState<Record<string, {
    chunk_ok: boolean;
    file_ok: boolean;
    expected?: string;
    error?: string;
  }>>({});
  const [fileLoading, setFileLoading] = useState<string | null>(null);
  const [fileVerifyProgress, setFileVerifyProgress] = useState<{
    total: number;
    done: number;
  } | null>(null);
  const [resetPassword, setResetPassword] = useState<{
    user: User;
    password: string;
  } | null>(null);
  const [tempPasswords, setTempPasswords] = useState<Record<number, string>>({});
  const [userQuery, setUserQuery] = useState("");
  const [userRole, setUserRole] = useState<"all" | "user" | "dev" | "admin">("all");
  const [submissionQuery, setSubmissionQuery] = useState("");
  const [submissionStatus, setSubmissionStatus] = useState<
    "all" | "pending" | "approved" | "rejected"
  >("pending");
  const [submissionPlatform, setSubmissionPlatform] = useState("all");
  const [submissionChannel, setSubmissionChannel] = useState("all");
  const [submissionSlaFilter, setSubmissionSlaFilter] = useState<"all" | "warn" | "crit">("all");
  const [selectedSubmissionIds, setSelectedSubmissionIds] = useState<number[]>([]);
  const [gameQuery, setGameQuery] = useState("");
  const [gamePrice, setGamePrice] = useState<"all" | "free" | "paid" | "sale">("all");
  const [autoRefresh, setAutoRefresh] = useState(true);

  const isAuthed = !!accessToken && !!me;

  useEffect(() => {
    const storedAccess = sessionStorage.getItem(TOKEN_KEY);
    const storedRefresh = sessionStorage.getItem(REFRESH_KEY);
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
        const res = await apiFetch("/api/auth/me", { method: "GET" });
        if (!res.ok) {
          throw new Error("Login ungültig.");
        }
        const data = await res.json();
        if (data.user?.role !== "admin") {
          throw new Error("Kein Admin-Zugang.");
        }
        setMe(data.user);
        const refreshedAccess = sessionStorage.getItem(TOKEN_KEY);
        const refreshedRefresh = sessionStorage.getItem(REFRESH_KEY);
        if (refreshedAccess) setAccessToken(refreshedAccess);
        if (refreshedRefresh) setRefreshToken(refreshedRefresh);
      } catch (err: any) {
        setError(err.message || "Fehler beim Login.");
        setAccessToken(null);
        setRefreshToken(null);
        setMe(null);
        sessionStorage.removeItem(TOKEN_KEY);
        sessionStorage.removeItem(REFRESH_KEY);
      } finally {
        setLoading(false);
      }
    };
    init();
  }, [accessToken, refreshToken]);

  const loadData = useCallback(async () => {
    if (!accessToken) return;
    setLoading(true);
    setError(null);
    try {
      const [usersRes, subsRes, gamesRes, overviewRes, devUpgradesRes] = await Promise.all([
        apiFetch("/api/admin/users", { method: "GET" }),
        apiFetch("/api/admin/submissions", { method: "GET" }),
        fetch(`${API_BASE}/api/public/apps`),
        apiFetch("/api/admin/overview", { method: "GET" }),
        apiFetch("/api/admin/dev-upgrade-payments?limit=250", { method: "GET" }),
      ]);

      if (!usersRes.ok) throw new Error("User-Liste konnte nicht geladen werden.");
      if (!subsRes.ok) throw new Error("Game Anfragen konnten nicht geladen werden.");
      if (!gamesRes.ok) throw new Error("Games konnten nicht geladen werden.");

      const usersData = await usersRes.json();
      const subsData = await subsRes.json();
      const gamesData = await gamesRes.json();
      let overviewData: Overview | null = null;
      if (overviewRes.ok) {
        overviewData = await overviewRes.json();
      }
      let devUpgradeData: DevUpgradePayment[] = [];
      if (devUpgradesRes.ok) {
        const payload = await devUpgradesRes.json();
        devUpgradeData = payload.items || [];
      }

      setUsers(usersData.items || []);
      setSubmissions(subsData.items || []);
      setGames(gamesData || []);
      setOverview(overviewData);
      setDevUpgrades(devUpgradeData);
      setSelectedSubmissionIds([]);
      setManifest(null);
      setFilesPanel(null);
      setLastSync(
        new Date().toLocaleString("de-DE", {
          day: "2-digit",
          month: "2-digit",
          year: "numeric",
          hour: "2-digit",
          minute: "2-digit",
        })
      );
      if (overviewData) {
        setOverviewSync(
          new Date().toLocaleString("de-DE", {
            day: "2-digit",
            month: "2-digit",
            year: "numeric",
            hour: "2-digit",
            minute: "2-digit",
          })
        );
      }
    } catch (err: any) {
      setError(err.message || "Fehler beim Laden.");
    } finally {
      setLoading(false);
    }
  }, [accessToken]);

  useEffect(() => {
    if (isAuthed) {
      loadData();
    }
  }, [isAuthed, loadData]);

  useEffect(() => {
    if (!isAuthed || !autoRefresh) return;
    const handle = window.setInterval(() => {
      loadData();
    }, 60000);
    return () => window.clearInterval(handle);
  }, [isAuthed, autoRefresh, loadData]);

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
      sessionStorage.setItem(TOKEN_KEY, data.access_token);
      sessionStorage.setItem(REFRESH_KEY, data.refresh_token);
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
    sessionStorage.removeItem(TOKEN_KEY);
    sessionStorage.removeItem(REFRESH_KEY);
  };

  const resetUserPassword = async (user: User) => {
    if (!accessToken) return;
    if (!confirm(`Passwort für ${user.email} wirklich zurücksetzen?`)) return;
    setLoading(true);
    try {
      const res = await apiFetch(
        `/api/admin/users/${user.id}/reset-password`,
        { method: "POST", body: JSON.stringify({}) }
      );
      if (!res.ok) throw new Error("Passwort-Reset fehlgeschlagen.");
      const data = await res.json();
      setResetPassword({ user, password: data.password });
      setTempPasswords((prev) => ({ ...prev, [user.id]: data.password }));
      await loadData();
    } catch (err: any) {
      setError(err.message || "Passwort-Reset fehlgeschlagen.");
    } finally {
      setLoading(false);
    }
  };

  const updateUserRole = async (user: User, role: string) => {
    if (!accessToken) return;
    if (role === user.role) return;
    setLoading(true);
    try {
      const res = await apiFetch(
        `/api/admin/users/${user.id}/role`,
        { method: "POST", body: JSON.stringify({ role }) }
      );
      if (!res.ok) throw new Error("Rollen-Update fehlgeschlagen.");
      await loadData();
    } catch (err: any) {
      setError(err.message || "Rollen-Update fehlgeschlagen.");
    } finally {
      setLoading(false);
    }
  };

  const deleteUser = async (user: User) => {
    if (!accessToken) return;
    if (!confirm(`User ${user.email} wirklich löschen?`)) return;
    setLoading(true);
    try {
      const res = await apiFetch(`/api/admin/users/${user.id}`, { method: "DELETE" });
      if (!res.ok) throw new Error("User löschen fehlgeschlagen.");
      await loadData();
    } catch (err: any) {
      setError(err.message || "User löschen fehlgeschlagen.");
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
        { method: "POST" }
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
        { method: "GET" }
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

  const downloadSubmissionZip = async (submission: Submission) => {
    if (!accessToken) return;
    setLoading(true);
    try {
      const res = await apiFetch(
        `/api/admin/submissions/${submission.id}/files/zip`,
        { method: "GET" }
      );
      if (!res.ok) throw new Error("ZIP konnte nicht geladen werden.");
      const blob = await res.blob();
      const disposition = res.headers.get("Content-Disposition") || "";
      const match = disposition.match(/filename="?([^\";]+)"?/i);
      const filename = match?.[1] || `submission-${submission.id}.zip`;
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
    } catch (err: any) {
      setError(err.message || "ZIP Download fehlgeschlagen.");
    } finally {
      setLoading(false);
    }
  };

  const loadSubmissionFiles = async (submission: Submission) => {
    if (!accessToken) return;
    setLoading(true);
    try {
      const res = await apiFetch(
        `/api/admin/submissions/${submission.id}/files`,
        { method: "GET" }
      );
      if (!res.ok) throw new Error("Dateiliste konnte nicht geladen werden.");
      const data = (await res.json()) as SubmissionFilesResponse;
      setFilesPanel({ submission, info: data });
      setFileQuery("");
      setFileVerify({});
      setFileVerifyProgress(null);
    } catch (err: any) {
      setError(err.message || "Dateiliste konnte nicht geladen werden.");
    } finally {
      setLoading(false);
    }
  };

  const downloadSubmissionFile = async (submission: Submission, path: string) => {
    if (!accessToken) return;
    setFileLoading(path);
    try {
      const res = await apiFetch(
        `/api/admin/submissions/${submission.id}/files/download?path=${encodeURIComponent(path)}`,
        { method: "GET" }
      );
      if (!res.ok) throw new Error("Datei konnte nicht geladen werden.");
      const blob = await res.blob();
      const disposition = res.headers.get("Content-Disposition") || "";
      const match = disposition.match(/filename="?([^\";]+)"?/i);
      const filename = match?.[1] || path.split("/").pop() || `file-${submission.id}`;
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
    } catch (err: any) {
      setError(err.message || "Datei Download fehlgeschlagen.");
    } finally {
      setFileLoading(null);
    }
  };

  const verifySubmissionFile = async (submission: Submission, path: string) => {
    if (!accessToken) return;
    setFileLoading(path);
    try {
      const res = await apiFetch(
        `/api/admin/submissions/${submission.id}/files/verify?path=${encodeURIComponent(path)}`,
        { method: "POST" }
      );
      if (!res.ok) throw new Error("Verify fehlgeschlagen.");
      const data = await res.json();
      setFileVerify((prev) => ({ ...prev, [`${submission.id}:${path}`]: data }));
    } catch (err: any) {
      setError(err.message || "Verify fehlgeschlagen.");
    } finally {
      setFileLoading(null);
    }
  };

  const verifyAllSubmissionFiles = async () => {
    if (!accessToken || !filesPanel?.info?.files?.length) return;
    const targets = filteredFiles.length ? filteredFiles : filesPanel.info.files;
    setFileLoading("__all__");
    setError(null);
    setFileVerifyProgress({ total: targets.length, done: 0 });
    try {
      const batchRes = await apiFetch(
        `/api/admin/submissions/${filesPanel.submission.id}/files/verify-batch`,
        { method: "POST", body: JSON.stringify({ paths: targets.map((f) => f.path) }) }
      );
      if (batchRes.ok) {
        const data = (await batchRes.json()) as VerifyBatchResponse;
        const results = data.results || [];
        setFileVerify((prev) => {
          const next = { ...prev };
          for (const result of results) {
            if (!result.path) continue;
            next[`${filesPanel.submission.id}:${result.path}`] = {
              chunk_ok: !!result.chunk_ok,
              file_ok: !!result.file_ok,
              expected: result.expected,
              error: result.error,
            };
          }
          return next;
        });
        setFileVerifyProgress({ total: targets.length, done: targets.length });
        return;
      }

      for (const file of targets) {
        const res = await apiFetch(
          `/api/admin/submissions/${filesPanel.submission.id}/files/verify?path=${encodeURIComponent(
            file.path
          )}`,
          { method: "POST" }
        );
        if (!res.ok) {
          throw new Error(`Verify fehlgeschlagen: ${file.path}`);
        }
        const data = await res.json();
        setFileVerify((prev) => ({
          ...prev,
          [`${filesPanel.submission.id}:${file.path}`]: data,
        }));
        setFileVerifyProgress((prev) =>
          prev ? { ...prev, done: Math.min(prev.done + 1, prev.total) } : prev
        );
      }
    } catch (err: any) {
      setError(err.message || "Verify fehlgeschlagen.");
    } finally {
      setFileLoading(null);
    }
  };

  const toggleSubmissionSelection = (id: number) => {
    setSelectedSubmissionIds((prev) =>
      prev.includes(id) ? prev.filter((item) => item !== id) : [...prev, id]
    );
  };

  const addSelectedSubmissions = (ids: number[]) => {
    if (!ids.length) return;
    setSelectedSubmissionIds((prev) => Array.from(new Set([...prev, ...ids])));
  };

  const removeSelectedSubmissions = (ids: number[]) => {
    if (!ids.length) return;
    setSelectedSubmissionIds((prev) => prev.filter((id) => !ids.includes(id)));
  };

  const clearSelectedSubmissions = () => {
    setSelectedSubmissionIds([]);
  };

  const bulkUpdateSubmissions = async (approve: boolean) => {
    if (!accessToken) return;
    if (!selectedSubmissionIds.length) return;
    const verb = approve ? "approve" : "reject";
    const label = approve ? "approve" : "reject";
    const targetStatus = approve ? "approved" : "rejected";
    const targets = selectedSubmissionIds.filter((id) => {
      const item = submissions.find((submission) => submission.id === id);
      return item ? item.status !== targetStatus : false;
    });
    if (!targets.length) {
      setError("Auswahl enthält keine passenden Submissions.");
      return;
    }
    if (!confirm(`${targets.length} Submissions wirklich ${label}?`)) return;
    setLoading(true);
    setError(null);
    try {
      let failed = 0;
      for (const id of targets) {
        const res = await apiFetch(`/api/admin/submissions/${id}/${verb}`, { method: "POST" });
        if (!res.ok) failed += 1;
      }
      if (failed) {
        throw new Error(`${failed} Aktionen fehlgeschlagen.`);
      }
      clearSelectedSubmissions();
      await loadData();
    } catch (err: any) {
      setError(err.message || "Bulk-Aktion fehlgeschlagen.");
    } finally {
      setLoading(false);
    }
  };

  const stats = useMemo(() => {
    const pending =
      overview?.submissions?.pending ?? submissions.filter((s) => s.status === "pending").length;
    const userCount = overview?.users?.total ?? users.length;
    const gameCount = overview?.apps?.total ?? games.length;
    return [
      { label: "Users", value: userCount },
      { label: "Anfragen", value: pending },
      { label: "Games", value: gameCount },
    ];
  }, [overview, users, submissions, games]);

  const overviewCards = useMemo(() => {
    if (!overview) return [];
    return [
      {
        label: "Umsatz gesamt",
        value: formatCurrency(overview.purchases.revenue_total),
        meta: `${overview.purchases.total} Käufe`,
      },
      {
        label: "Umsatz 30 Tage",
        value: formatCurrency(overview.purchases.revenue_30d),
        meta: `${overview.purchases.count_30d} Käufe`,
      },
      {
        label: "Apps freigegeben",
        value: `${overview.apps.approved}`,
        meta: `${overview.apps.pending} pending`,
      },
      {
        label: "Submissions offen",
        value: `${overview.submissions.pending}`,
        meta: `${overview.submissions.total} total`,
      },
      {
        label: "Admins",
        value: `${overview.users.admins}`,
        meta: `${overview.users.devs} Devs`,
      },
      {
        label: "Users total",
        value: `${overview.users.total}`,
        meta: `${overview.users.users} User`,
      },
      {
        label: "Dev-Upgrades",
        value: `${overview.dev_upgrade_payments?.total ?? 0}`,
        meta: `${formatCurrency(overview.dev_upgrade_payments?.amount_total ?? 0)} Gesamt`,
      },
    ];
  }, [overview]);

  const platformOptions = useMemo(() => {
    const values = new Set(submissions.map((submission) => submission.platform).filter(Boolean));
    return Array.from(values).sort();
  }, [submissions]);

  const channelOptions = useMemo(() => {
    const values = new Set(submissions.map((submission) => submission.channel).filter(Boolean));
    return Array.from(values).sort();
  }, [submissions]);

  const submissionCounts = useMemo(() => {
    if (overview?.submissions) {
      return {
        pending: overview.submissions.pending,
        approved: overview.submissions.approved,
        rejected: overview.submissions.rejected,
        total: overview.submissions.total,
      };
    }
    return submissions.reduce(
      (acc, submission) => {
        const status = submission.status as "pending" | "approved" | "rejected";
        if (status in acc) acc[status] += 1;
        acc.total += 1;
        return acc;
      },
      { pending: 0, approved: 0, rejected: 0, total: 0 }
    );
  }, [overview, submissions]);

  const submissionSlaCounts = useMemo(() => {
    return submissions.reduce(
      (acc, submission) => {
        if (submission.status !== "pending") return acc;
        const tone = submissionAgeTone(submission.created_at);
        if (tone === "warn") acc.warn += 1;
        if (tone === "crit") acc.crit += 1;
        return acc;
      },
      { warn: 0, crit: 0 }
    );
  }, [submissions]);

  const filteredUsers = useMemo(() => {
    const query = userQuery.trim().toLowerCase();
    return users.filter((user) => {
      if (userRole !== "all" && user.role !== userRole) return false;
      if (!query) return true;
      return (
        user.email?.toLowerCase().includes(query) ||
        user.username?.toLowerCase().includes(query) ||
        `${user.id}`.includes(query)
      );
    });
  }, [users, userQuery, userRole]);

  const filteredSubmissions = useMemo(() => {
    const query = submissionQuery.trim().toLowerCase();
    const filtered = submissions.filter((submission) => {
      if (submissionStatus !== "all" && submission.status !== submissionStatus) return false;
      if (submissionPlatform !== "all" && submission.platform !== submissionPlatform) return false;
      if (submissionChannel !== "all" && submission.channel !== submissionChannel) return false;
      if (submissionSlaFilter !== "all") {
        if (submission.status !== "pending") return false;
        const tone = submissionAgeTone(submission.created_at);
        if (submissionSlaFilter === "warn" && tone === "ok") return false;
        if (submissionSlaFilter === "crit" && tone !== "crit") return false;
      }
      if (!query) return true;
      return (
        submission.app_slug.toLowerCase().includes(query) ||
        submission.version.toLowerCase().includes(query) ||
        submission.platform.toLowerCase().includes(query) ||
        submission.channel.toLowerCase().includes(query)
      );
    });
    return [...filtered].sort((a, b) => {
      const ta = a.created_at ? new Date(a.created_at).getTime() : 0;
      const tb = b.created_at ? new Date(b.created_at).getTime() : 0;
      if (ta !== tb) return tb - ta;
      return (b.id || 0) - (a.id || 0);
    });
  }, [
    submissions,
    submissionQuery,
    submissionStatus,
    submissionPlatform,
    submissionChannel,
    submissionSlaFilter,
  ]);

  const selectedSubmissionSet = useMemo(
    () => new Set(selectedSubmissionIds),
    [selectedSubmissionIds]
  );

  useEffect(() => {
    setSelectedSubmissionIds([]);
  }, [submissionQuery, submissionStatus, submissionPlatform, submissionChannel, submissionSlaFilter]);

  const filteredGames = useMemo(() => {
    const query = gameQuery.trim().toLowerCase();
    return games.filter((game) => {
      if (gamePrice === "free" && game.price > 0) return false;
      if (gamePrice === "paid" && game.price <= 0) return false;
      if (gamePrice === "sale" && (!game.sale_percent || game.sale_percent <= 0)) return false;
      if (!query) return true;
      return (
        game.title?.toLowerCase().includes(query) ||
        game.slug?.toLowerCase().includes(query) ||
        game.description?.toLowerCase().includes(query)
      );
    });
  }, [games, gameQuery, gamePrice]);

  const filteredFiles = useMemo(() => {
    if (!filesPanel?.info?.files) return [];
    const query = fileQuery.trim().toLowerCase();
    if (!query) return filesPanel.info.files;
    return filesPanel.info.files.filter((file) =>
      file.path.toLowerCase().includes(query)
    );
  }, [filesPanel, fileQuery]);

  const totalFilesSize = useMemo(() => {
    if (!filesPanel?.info?.files?.length) return 0;
    return filesPanel.info.files.reduce((sum, file) => sum + (file.size || 0), 0);
  }, [filesPanel]);

  const fileVerifySummary = useMemo(() => {
    if (!filesPanel?.info?.files?.length) return null;
    let okCount = 0;
    let warnCount = 0;
    let errorCount = 0;
    let checked = 0;
    for (const file of filesPanel.info.files) {
      const key = `${filesPanel.submission.id}:${file.path}`;
      const verify = fileVerify[key];
      if (!verify) continue;
      checked += 1;
      if (verify.error) {
        errorCount += 1;
      } else if (verify.chunk_ok && verify.file_ok) {
        okCount += 1;
      } else {
        warnCount += 1;
      }
    }
    return { okCount, warnCount, errorCount, checked, total: filesPanel.info.files.length };
  }, [filesPanel, fileVerify]);

  return (
    <div className="min-h-screen px-6 py-10">
      <div className="mx-auto flex w-full max-w-6xl flex-col gap-8">
        <header className="flex flex-col gap-5 rounded-3xl border border-[var(--stroke)] bg-[var(--bg-elev)]/60 p-6">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
            <div className="space-y-2">
              <p className="text-xs uppercase tracking-[0.4em] text-[var(--muted)]">
                Indie-Hain Admin
              </p>
              <h1 className="text-4xl font-semibold text-[var(--ink)]">
                Ops Dashboard
              </h1>
              <p className="text-sm text-[var(--muted)]">
                Kontrolle über Nutzer, Game-Uploads und Live-Katalog.
              </p>
            </div>
            {isAuthed && me ? (
              <div className="flex flex-wrap items-center gap-3">
                <span className="rounded-full border border-[var(--stroke)] bg-[var(--bg-soft)] px-4 py-2 text-sm text-[var(--muted)]">
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
          </div>
          <div className="grid gap-3 text-xs text-[var(--muted)] md:grid-cols-3">
            <div className="rounded-2xl border border-[var(--stroke)] bg-[var(--bg-soft)] px-4 py-3">
              <p className="uppercase tracking-[0.25em]">API Base</p>
              <p className="mt-2 truncate text-sm text-[var(--ink)]">{API_BASE}</p>
            </div>
            <div className="rounded-2xl border border-[var(--stroke)] bg-[var(--bg-soft)] px-4 py-3">
              <p className="uppercase tracking-[0.25em]">Letzter Sync</p>
              <p className="mt-2 text-sm text-[var(--ink)]">
                {lastSync || "—"}
              </p>
            </div>
            <div className="rounded-2xl border border-[var(--stroke)] bg-[var(--bg-soft)] px-4 py-3">
              <p className="uppercase tracking-[0.25em]">Status</p>
              <p className="mt-2 text-sm text-[var(--ink)]">
                {loading ? "Aktualisiert..." : isAuthed ? "Bereit" : "Login nötig"}
              </p>
            </div>
          </div>
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

            {overview ? (
              <section className="card rounded-3xl p-6">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <p className="text-xs uppercase tracking-[0.3em] text-[var(--muted)]">
                      Ops Snapshot
                    </p>
                    <p className="mt-1 text-sm text-[var(--muted)]">
                      Live KPI-Stand aus dem Backend.
                    </p>
                  </div>
                  <div className="text-xs text-[var(--muted)]">
                    Stand: <span className="text-[var(--ink)]">{overviewSync || "—"}</span>
                  </div>
                </div>
                <div className="mt-4 grid gap-3 md:grid-cols-3">
                  {overviewCards.map((card) => (
                    <div
                      key={card.label}
                      className="rounded-2xl border border-[var(--stroke)] bg-[var(--bg-soft)] px-4 py-3 text-sm text-[var(--muted)]"
                    >
                      <p className="uppercase tracking-[0.2em]">{card.label}</p>
                      <p className="mt-2 text-xl text-[var(--ink)]">{card.value}</p>
                      <p className="mt-1 text-xs text-[var(--muted)]">{card.meta}</p>
                    </div>
                  ))}
                </div>
                <div className="mt-4 grid gap-3 text-xs text-[var(--muted)] md:grid-cols-4">
                  <div className="rounded-2xl border border-[var(--stroke)] bg-[var(--bg-soft)] px-4 py-3">
                    <p className="uppercase tracking-[0.2em]">Letzter User</p>
                    <p className="mt-2 text-sm text-[var(--ink)]">
                      {formatTimestamp(overview.last_activity?.user)}
                    </p>
                  </div>
                  <div className="rounded-2xl border border-[var(--stroke)] bg-[var(--bg-soft)] px-4 py-3">
                    <p className="uppercase tracking-[0.2em]">Letzte Submission</p>
                    <p className="mt-2 text-sm text-[var(--ink)]">
                      {formatTimestamp(overview.last_activity?.submission)}
                    </p>
                  </div>
                  <div className="rounded-2xl border border-[var(--stroke)] bg-[var(--bg-soft)] px-4 py-3">
                    <p className="uppercase tracking-[0.2em]">Letzter Kauf</p>
                    <p className="mt-2 text-sm text-[var(--ink)]">
                      {formatTimestamp(overview.last_activity?.purchase)}
                    </p>
                  </div>
                  <div className="rounded-2xl border border-[var(--stroke)] bg-[var(--bg-soft)] px-4 py-3">
                    <p className="uppercase tracking-[0.2em]">Letzter Dev-Upgrade</p>
                    <p className="mt-2 text-sm text-[var(--ink)]">
                      {formatTimestamp(overview.last_activity?.dev_upgrade_payment)}
                    </p>
                  </div>
                </div>
              </section>
            ) : null}

            <section className="card rounded-3xl p-6">
              <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[var(--stroke)] pb-4">
                <div className="flex items-center gap-2">
                  {(["users", "submissions", "games", "dev_upgrades"] as const).map((key) => (
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
                        : key === "games"
                        ? "Games"
                        : "Dev-Upgrades"}
                    </button>
                  ))}
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <button
                    onClick={() => {
                      setUserQuery("");
                      setUserRole("all");
                      setSubmissionQuery("");
                      setSubmissionStatus("pending");
                      setSubmissionPlatform("all");
                      setSubmissionChannel("all");
                      setSubmissionSlaFilter("all");
                      setGameQuery("");
                      setGamePrice("all");
                    }}
                    className="rounded-full border border-[var(--stroke)] px-4 py-2 text-sm text-[var(--muted)] hover:border-[var(--accent)]"
                  >
                    Filter zurücksetzen
                  </button>
                  <button
                    onClick={loadData}
                    className="rounded-full border border-[var(--stroke)] px-4 py-2 text-sm text-[var(--muted)] hover:border-[var(--accent)]"
                  >
                    {loading ? "Lädt..." : "Aktualisieren"}
                  </button>
                  <button
                    onClick={() => setAutoRefresh((prev) => !prev)}
                    className={`rounded-full px-4 py-2 text-sm transition ${
                      autoRefresh
                        ? "bg-[var(--accent)] text-black"
                        : "border border-[var(--stroke)] text-[var(--muted)] hover:border-[var(--accent)]"
                    }`}
                  >
                    Auto-Refresh {autoRefresh ? "On" : "Off"}
                  </button>
                </div>
              </div>

              {error ? (
                <div className="mt-4 rounded-2xl border border-[var(--danger)]/40 bg-[rgba(255,107,107,0.1)] px-4 py-3 text-sm text-[var(--danger)]">
                  {error}
                </div>
              ) : null}

              {tab === "users" ? (
                <>
                  <div className="mt-5 grid gap-3 md:grid-cols-4">
                    <div className="space-y-2">
                      <label className="text-xs uppercase tracking-[0.2em] text-[var(--muted)]">
                        Suche
                      </label>
                      <input
                        value={userQuery}
                        onChange={(e) => setUserQuery(e.target.value)}
                        placeholder="E-Mail, Username, ID"
                        className="w-full rounded-2xl border border-[var(--stroke)] bg-[var(--bg-soft)] px-4 py-3 text-sm text-[var(--ink)] outline-none focus:border-[var(--accent)]"
                      />
                    </div>
                    <div className="space-y-2">
                      <label className="text-xs uppercase tracking-[0.2em] text-[var(--muted)]">
                        Rolle
                      </label>
                      <select
                        value={userRole}
                        onChange={(e) => setUserRole(e.target.value as typeof userRole)}
                        className="w-full rounded-2xl border border-[var(--stroke)] bg-[var(--bg-soft)] px-4 py-3 text-sm text-[var(--ink)]"
                      >
                        <option value="all">Alle Rollen</option>
                        <option value="user">user</option>
                        <option value="dev">dev</option>
                        <option value="admin">admin</option>
                      </select>
                    </div>
                    <div className="rounded-2xl border border-[var(--stroke)] bg-[var(--bg-soft)] px-4 py-3 text-sm text-[var(--muted)]">
                      <p className="uppercase tracking-[0.2em]">Treffer</p>
                      <p className="mt-2 text-xl text-[var(--ink)]">
                        {filteredUsers.length} User
                      </p>
                    </div>
                  </div>
                  <UsersTable
                    users={filteredUsers}
                  tempPasswords={tempPasswords}
                  onReset={resetUserPassword}
                  onRoleChange={updateUserRole}
                  onDelete={deleteUser}
                  />
                </>
              ) : null}

              {tab === "submissions" ? (
                <>
                  <div className="mt-5 grid gap-3 md:grid-cols-5">
                    <div className="space-y-2">
                      <label className="text-xs uppercase tracking-[0.2em] text-[var(--muted)]">
                        Suche
                      </label>
                      <input
                        value={submissionQuery}
                        onChange={(e) => setSubmissionQuery(e.target.value)}
                        placeholder="Slug, Version, Platform"
                        className="w-full rounded-2xl border border-[var(--stroke)] bg-[var(--bg-soft)] px-4 py-3 text-sm text-[var(--ink)] outline-none focus:border-[var(--accent)]"
                      />
                    </div>
                    <div className="space-y-2">
                      <label className="text-xs uppercase tracking-[0.2em] text-[var(--muted)]">
                        Status
                      </label>
                      <select
                        value={submissionStatus}
                        onChange={(e) =>
                          setSubmissionStatus(e.target.value as typeof submissionStatus)
                        }
                        className="w-full rounded-2xl border border-[var(--stroke)] bg-[var(--bg-soft)] px-4 py-3 text-sm text-[var(--ink)]"
                      >
                        <option value="all">Alle</option>
                        <option value="pending">pending</option>
                        <option value="approved">approved</option>
                        <option value="rejected">rejected</option>
                      </select>
                    </div>
                    <div className="space-y-2">
                      <label className="text-xs uppercase tracking-[0.2em] text-[var(--muted)]">
                        Platform
                      </label>
                      <select
                        value={submissionPlatform}
                        onChange={(e) => setSubmissionPlatform(e.target.value)}
                        className="w-full rounded-2xl border border-[var(--stroke)] bg-[var(--bg-soft)] px-4 py-3 text-sm text-[var(--ink)]"
                      >
                        <option value="all">Alle</option>
                        {platformOptions.map((platform) => (
                          <option key={platform} value={platform}>
                            {platform}
                          </option>
                        ))}
                      </select>
                    </div>
                    <div className="space-y-2">
                      <label className="text-xs uppercase tracking-[0.2em] text-[var(--muted)]">
                        Channel
                      </label>
                      <select
                        value={submissionChannel}
                        onChange={(e) => setSubmissionChannel(e.target.value)}
                        className="w-full rounded-2xl border border-[var(--stroke)] bg-[var(--bg-soft)] px-4 py-3 text-sm text-[var(--ink)]"
                      >
                        <option value="all">Alle</option>
                        {channelOptions.map((channel) => (
                          <option key={channel} value={channel}>
                            {channel}
                          </option>
                        ))}
                      </select>
                    </div>
                    <div className="rounded-2xl border border-[var(--stroke)] bg-[var(--bg-soft)] px-4 py-3 text-sm text-[var(--muted)]">
                      <p className="uppercase tracking-[0.2em]">Treffer</p>
                      <p className="mt-2 text-xl text-[var(--ink)]">
                        {filteredSubmissions.length} Anfragen
                      </p>
                    </div>
                  </div>
                  <div className="mt-4 flex flex-wrap items-center gap-2 text-xs text-[var(--muted)]">
                    <span className="uppercase tracking-[0.2em]">Quick Status</span>
                    <button
                      onClick={() => setSubmissionStatus("pending")}
                      className={`rounded-full px-3 py-1 uppercase tracking-[0.2em] ${
                        submissionStatus === "pending"
                          ? "bg-[var(--accent)] text-black"
                          : "border border-[var(--stroke)] hover:border-[var(--accent)]"
                      }`}
                    >
                      Pending {submissionCounts.pending}
                    </button>
                    <button
                      onClick={() => setSubmissionStatus("approved")}
                      className={`rounded-full px-3 py-1 uppercase tracking-[0.2em] ${
                        submissionStatus === "approved"
                          ? "bg-[var(--accent-2)] text-black"
                          : "border border-[var(--stroke)] hover:border-[var(--accent-2)]"
                      }`}
                    >
                      Approved {submissionCounts.approved}
                    </button>
                    <button
                      onClick={() => setSubmissionStatus("rejected")}
                      className={`rounded-full px-3 py-1 uppercase tracking-[0.2em] ${
                        submissionStatus === "rejected"
                          ? "bg-[var(--danger)] text-black"
                          : "border border-[var(--stroke)] hover:border-[var(--danger)]"
                      }`}
                    >
                      Rejected {submissionCounts.rejected}
                    </button>
                    <button
                      onClick={() => setSubmissionStatus("all")}
                      className={`rounded-full px-3 py-1 uppercase tracking-[0.2em] ${
                        submissionStatus === "all"
                          ? "bg-[var(--bg-elev)] text-[var(--ink)]"
                          : "border border-[var(--stroke)] hover:border-[var(--ink)]"
                      }`}
                    >
                      Alle {submissionCounts.total}
                    </button>
                  </div>
                  <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-[var(--muted)]">
                    <span className="uppercase tracking-[0.2em]">SLA Filter</span>
                    <button
                      onClick={() => setSubmissionSlaFilter("warn")}
                      className={`rounded-full px-3 py-1 uppercase tracking-[0.2em] ${
                        submissionSlaFilter === "warn"
                          ? "bg-[rgba(240,198,107,0.3)] text-[var(--accent-warm)]"
                          : "border border-[var(--stroke)] hover:border-[var(--accent-warm)]"
                      }`}
                    >
                      &gt;24h {submissionSlaCounts.warn + submissionSlaCounts.crit}
                    </button>
                    <button
                      onClick={() => setSubmissionSlaFilter("crit")}
                      className={`rounded-full px-3 py-1 uppercase tracking-[0.2em] ${
                        submissionSlaFilter === "crit"
                          ? "bg-[rgba(255,107,107,0.25)] text-[var(--danger)]"
                          : "border border-[var(--stroke)] hover:border-[var(--danger)]"
                      }`}
                    >
                      &gt;72h {submissionSlaCounts.crit}
                    </button>
                    <button
                      onClick={() => setSubmissionSlaFilter("all")}
                      className={`rounded-full px-3 py-1 uppercase tracking-[0.2em] ${
                        submissionSlaFilter === "all"
                          ? "bg-[var(--bg-elev)] text-[var(--ink)]"
                          : "border border-[var(--stroke)] hover:border-[var(--ink)]"
                      }`}
                    >
                      Alle
                    </button>
                  </div>
                  <div className="mt-4 flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-[var(--stroke)] bg-[var(--bg-soft)] px-4 py-3 text-sm">
                    <div className="text-[var(--muted)]">
                      Auswahl:{" "}
                      <span className="text-[var(--ink)]">
                        {selectedSubmissionIds.length}
                      </span>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      <button
                        onClick={() =>
                          addSelectedSubmissions(filteredSubmissions.map((s) => s.id))
                        }
                        className="rounded-full border border-[var(--stroke)] px-3 py-1 text-xs text-[var(--muted)] hover:border-[var(--accent)]"
                      >
                        Alle gefilterten
                      </button>
                      <button
                        onClick={clearSelectedSubmissions}
                        className="rounded-full border border-[var(--stroke)] px-3 py-1 text-xs text-[var(--muted)] hover:border-[var(--accent)]"
                      >
                        Auswahl löschen
                      </button>
                      <button
                        onClick={() => bulkUpdateSubmissions(true)}
                        disabled={!selectedSubmissionIds.length || loading}
                        className="rounded-full bg-[var(--accent)] px-3 py-1 text-xs font-semibold text-black disabled:opacity-50"
                      >
                        Approve
                      </button>
                      <button
                        onClick={() => bulkUpdateSubmissions(false)}
                        disabled={!selectedSubmissionIds.length || loading}
                        className="rounded-full border border-[var(--danger)]/50 px-3 py-1 text-xs text-[var(--danger)] disabled:opacity-50"
                      >
                        Reject
                      </button>
                    </div>
                  </div>
                  <SubmissionsTable
                    submissions={filteredSubmissions}
                    selectedIds={selectedSubmissionSet}
                    onToggleSelection={toggleSubmissionSelection}
                    onSelectAll={addSelectedSubmissions}
                    onClearSection={removeSelectedSubmissions}
                    onApprove={(s) => approveSubmission(s, true)}
                    onReject={(s) => approveSubmission(s, false)}
                    onManifest={loadManifest}
                    onFiles={loadSubmissionFiles}
                    onDownloadZip={downloadSubmissionZip}
                  />
                </>
              ) : null}

              {tab === "games" ? (
                <>
                  <div className="mt-5 grid gap-3 md:grid-cols-3">
                    <div className="space-y-2 md:col-span-2">
                      <label className="text-xs uppercase tracking-[0.2em] text-[var(--muted)]">
                        Suche
                      </label>
                      <input
                        value={gameQuery}
                        onChange={(e) => setGameQuery(e.target.value)}
                        placeholder="Titel, Slug, Beschreibung"
                        className="w-full rounded-2xl border border-[var(--stroke)] bg-[var(--bg-soft)] px-4 py-3 text-sm text-[var(--ink)] outline-none focus:border-[var(--accent)]"
                      />
                    </div>
                    <div className="space-y-2">
                      <label className="text-xs uppercase tracking-[0.2em] text-[var(--muted)]">
                        Preisfilter
                      </label>
                      <select
                        value={gamePrice}
                        onChange={(e) => setGamePrice(e.target.value as typeof gamePrice)}
                        className="w-full rounded-2xl border border-[var(--stroke)] bg-[var(--bg-soft)] px-4 py-3 text-sm text-[var(--ink)]"
                      >
                        <option value="all">Alle</option>
                        <option value="free">Free</option>
                        <option value="paid">Paid</option>
                        <option value="sale">Sale</option>
                      </select>
                    </div>
                    <div className="rounded-2xl border border-[var(--stroke)] bg-[var(--bg-soft)] px-4 py-3 text-sm text-[var(--muted)]">
                      <p className="uppercase tracking-[0.2em]">Treffer</p>
                      <p className="mt-2 text-xl text-[var(--ink)]">
                        {filteredGames.length} Games
                      </p>
                    </div>
                  </div>
                  <GamesTable games={filteredGames} />
                </>
              ) : null}

              {tab === "dev_upgrades" ? (
                <>
                  <div className="mt-5 grid gap-3 md:grid-cols-4">
                    <div className="rounded-2xl border border-[var(--stroke)] bg-[var(--bg-soft)] px-4 py-3 text-sm text-[var(--muted)]">
                      <p className="uppercase tracking-[0.2em]">Einträge</p>
                      <p className="mt-2 text-xl text-[var(--ink)]">
                        {overview?.dev_upgrade_payments?.total ?? devUpgrades.length}
                      </p>
                    </div>
                    <div className="rounded-2xl border border-[var(--stroke)] bg-[var(--bg-soft)] px-4 py-3 text-sm text-[var(--muted)]">
                      <p className="uppercase tracking-[0.2em]">Offen</p>
                      <p className="mt-2 text-xl text-[var(--ink)]">
                        {overview?.dev_upgrade_payments?.open ?? 0}
                      </p>
                    </div>
                    <div className="rounded-2xl border border-[var(--stroke)] bg-[var(--bg-soft)] px-4 py-3 text-sm text-[var(--muted)]">
                      <p className="uppercase tracking-[0.2em]">Verbraucht</p>
                      <p className="mt-2 text-xl text-[var(--ink)]">
                        {overview?.dev_upgrade_payments?.consumed ?? 0}
                      </p>
                    </div>
                    <div className="rounded-2xl border border-[var(--stroke)] bg-[var(--bg-soft)] px-4 py-3 text-sm text-[var(--muted)]">
                      <p className="uppercase tracking-[0.2em]">Betrag gesamt</p>
                      <p className="mt-2 text-xl text-[var(--ink)]">
                        {formatCurrency(overview?.dev_upgrade_payments?.amount_total ?? 0)}
                      </p>
                    </div>
                  </div>
                  <DevUpgradePaymentsTable payments={devUpgrades} />
                </>
              ) : null}
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
              {manifest.files?.length ? (
                <div className="rounded-xl border border-[var(--stroke)] bg-[var(--bg-soft)] p-3 text-xs text-[var(--muted)]">
                  <p className="uppercase tracking-[0.2em] text-[var(--ink)]">
                    Preview
                  </p>
                  <ul className="mt-2 space-y-1">
                    {manifest.files.slice(0, 6).map((file) => (
                      <li key={file.path} className="flex items-center justify-between">
                        <span className="truncate">{file.path}</span>
                        <span className="ml-3 text-[var(--muted)]">
                          {formatBytes(file.size)}
                        </span>
                      </li>
                    ))}
                  </ul>
                  {manifest.files.length > 6 ? (
                    <p className="mt-2 text-[var(--muted)]">
                      + {manifest.files.length - 6} weitere Dateien
                    </p>
                  ) : null}
                </div>
              ) : null}
            </div>
          }
        />
      ) : null}

      {filesPanel ? (
        <Modal
          title="Submission Files"
          onClose={() => setFilesPanel(null)}
          content={
            <div className="space-y-3 text-sm text-[var(--muted)]">
              <div className="grid gap-2 md:grid-cols-2">
                <p>
                  <span className="text-[var(--ink)]">App:</span>{" "}
                  {filesPanel.info.app || filesPanel.submission.app_slug}
                </p>
                <p>
                  <span className="text-[var(--ink)]">Version:</span>{" "}
                  {filesPanel.info.version || filesPanel.submission.version}
                </p>
                <p>
                  <span className="text-[var(--ink)]">Files:</span>{" "}
                  {filesPanel.info.files?.length || 0}
                </p>
                <p>
                  <span className="text-[var(--ink)]">Total Size:</span>{" "}
                  {formatBytes(totalFilesSize)}
                </p>
              </div>

              <div className="flex flex-wrap items-center gap-3">
                <input
                  value={fileQuery}
                  onChange={(e) => setFileQuery(e.target.value)}
                  placeholder="Datei suchen..."
                  className="w-full rounded-2xl border border-[var(--stroke)] bg-[var(--bg-soft)] px-4 py-2 text-sm text-[var(--ink)] outline-none focus:border-[var(--accent)] md:max-w-sm"
                />
                <button
                  onClick={verifyAllSubmissionFiles}
                  disabled={fileLoading === "__all__" || !filteredFiles.length}
                  className="rounded-full border border-[var(--stroke)] px-3 py-1 text-[10px] uppercase tracking-[0.2em] text-[var(--muted)] disabled:opacity-50"
                >
                  {fileLoading === "__all__" ? "Prüft..." : "Verify gefilterte"}
                </button>
                {fileVerifyProgress ? (
                  <div className="text-xs text-[var(--muted)]">
                    Verify:{" "}
                    <span className="text-[var(--ink)]">
                      {fileVerifyProgress.done}/{fileVerifyProgress.total}
                    </span>
                  </div>
                ) : null}
                {fileVerifySummary ? (
                  <div className="text-xs text-[var(--muted)]">
                    Geprüft:{" "}
                    <span className="text-[var(--ink)]">
                      {fileVerifySummary.checked}/{fileVerifySummary.total}
                    </span>{" "}
                    · OK{" "}
                    <span className="text-[var(--accent)]">{fileVerifySummary.okCount}</span>{" "}
                    · Warn{" "}
                    <span className="text-[var(--accent-warm)]">{fileVerifySummary.warnCount}</span>{" "}
                    · Fehler{" "}
                    <span className="text-[var(--danger)]">{fileVerifySummary.errorCount}</span>
                  </div>
                ) : null}
                <div className="text-xs text-[var(--muted)]">
                  Treffer:{" "}
                  <span className="text-[var(--ink)]">{filteredFiles.length}</span>
                </div>
              </div>

              <div className="max-h-[360px] space-y-2 overflow-auto rounded-2xl border border-[var(--stroke)] bg-[var(--bg-soft)] p-3 text-xs">
                {filteredFiles.length ? (
                  filteredFiles.map((file) => {
                    const verifyKey = `${filesPanel.submission.id}:${file.path}`;
                    const verify = fileVerify[verifyKey];
                    const status =
                      verify
                        ? verify.error
                          ? "Error"
                          : verify.chunk_ok && verify.file_ok
                          ? "OK"
                          : verify.chunk_ok
                          ? "Chunk OK"
                          : "Fehler"
                        : "—";
                    return (
                      <div
                        key={file.path}
                        className="flex flex-col gap-2 rounded-xl border border-[var(--stroke)]/60 bg-[var(--bg-elev)]/60 px-3 py-2"
                      >
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <div className="min-w-0">
                            <p className="truncate font-mono text-[var(--ink)]">{file.path}</p>
                            <p className="text-[var(--muted)]">
                              {formatBytes(file.size || 0)} · Status:{" "}
                              <span className="text-[var(--ink)]">{status}</span>
                            </p>
                            {verify?.error ? (
                              <p className="text-[var(--danger)]">Fehler: {verify.error}</p>
                            ) : null}
                            <p className="text-[var(--muted)]">
                              {file.sha256 ? (
                                <>
                                  SHA: <span className="text-[var(--ink)]">{shortHash(file.sha256)}</span>
                                </>
                              ) : (
                                "SHA: —"
                              )}
                              {" · "}Chunks: <span className="text-[var(--ink)]">{file.chunks?.length || 0}</span>
                            </p>
                          </div>
                          <div className="flex flex-wrap gap-2">
                            <button
                              onClick={() =>
                                navigator.clipboard.writeText(file.path)
                              }
                              className="rounded-full border border-[var(--stroke)] px-3 py-1 text-[10px] uppercase tracking-[0.2em] text-[var(--muted)]"
                            >
                              Copy Path
                            </button>
                            {file.sha256 ? (
                              <button
                                onClick={() => navigator.clipboard.writeText(file.sha256 || "")}
                                className="rounded-full border border-[var(--stroke)] px-3 py-1 text-[10px] uppercase tracking-[0.2em] text-[var(--muted)]"
                              >
                                Copy SHA
                              </button>
                            ) : null}
                            <button
                              onClick={() =>
                                verifySubmissionFile(filesPanel.submission, file.path)
                              }
                              disabled={fileLoading === file.path}
                              className="rounded-full border border-[var(--stroke)] px-3 py-1 text-[10px] uppercase tracking-[0.2em] text-[var(--muted)] disabled:opacity-50"
                            >
                              {fileLoading === file.path ? "Prüft..." : "Verify"}
                            </button>
                            <button
                              onClick={() =>
                                downloadSubmissionFile(filesPanel.submission, file.path)
                              }
                              disabled={fileLoading === file.path}
                              className="rounded-full bg-[var(--accent)] px-3 py-1 text-[10px] uppercase tracking-[0.2em] text-black disabled:opacity-50"
                            >
                              {fileLoading === file.path ? "Lädt..." : "Download"}
                            </button>
                          </div>
                        </div>
                      </div>
                    );
                  })
                ) : (
                  <p className="text-[var(--muted)]">Keine Dateien gefunden.</p>
                )}
              </div>
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
  tempPasswords,
  onReset,
  onRoleChange,
  onDelete,
}: {
  users: User[];
  tempPasswords: Record<number, string>;
  onReset: (user: User) => void;
  onRoleChange: (user: User, role: string) => void;
  onDelete: (user: User) => void;
}) {
  if (!users.length) {
    return <p className="mt-6 text-sm text-[var(--muted)]">Keine User gefunden.</p>;
  }
  return (
    <div className="mt-6 overflow-x-auto">
      <table className="w-full text-left text-sm">
        <thead className="text-xs uppercase tracking-[0.2em] text-[var(--muted)]">
          <tr>
            <th className="pb-3">ID</th>
            <th className="pb-3">E-Mail</th>
            <th className="pb-3">Username</th>
            <th className="pb-3">Rolle</th>
            <th className="pb-3">Temp PW</th>
            <th className="pb-3">Aktion</th>
          </tr>
        </thead>
        <tbody className="text-[var(--ink)]">
          {users.map((user) => (
            <tr key={user.id} className="border-t border-[var(--stroke)]">
              <td className="py-3">{user.id}</td>
              <td className="py-3">{user.email}</td>
              <td className="py-3">{user.username || "-"}</td>
              <td className="py-3">
                <select
                  value={user.role}
                  onChange={(e) => onRoleChange(user, e.target.value)}
                  className="rounded-full border border-[var(--stroke)] bg-[var(--bg-soft)] px-3 py-1 text-xs uppercase tracking-[0.2em] text-[var(--ink)]"
                >
                  <option value="user">user</option>
                  <option value="dev">dev</option>
                  <option value="admin">admin</option>
                </select>
              </td>
              <td className="py-3">
                {user.force_password_reset && tempPasswords[user.id] ? (
                  <span className="rounded-full border border-[var(--stroke)] bg-[var(--bg-soft)] px-3 py-1 text-xs text-[var(--ink)]">
                    {tempPasswords[user.id]}
                  </span>
                ) : (
                  <span className="text-xs text-[var(--muted)]">—</span>
                )}
              </td>
              <td className="py-3">
                <div className="flex flex-wrap gap-2">
                  <button
                    onClick={() => onReset(user)}
                    className="rounded-full border border-[var(--stroke)] px-3 py-1 text-xs text-[var(--muted)] hover:border-[var(--accent)]"
                  >
                    Passwort Reset
                  </button>
                  <button
                    onClick={() => navigator.clipboard.writeText(user.email)}
                    className="rounded-full border border-[var(--stroke)] px-3 py-1 text-xs text-[var(--muted)] hover:border-[var(--accent)]"
                  >
                    Copy Mail
                  </button>
                  <button
                    onClick={() => onDelete(user)}
                    className="rounded-full border border-[var(--danger)]/60 px-3 py-1 text-xs text-[var(--danger)] hover:bg-[var(--danger)]/10"
                  >
                    Löschen
                  </button>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function DevUpgradePaymentsTable({ payments }: { payments: DevUpgradePayment[] }) {
  if (!payments.length) {
    return <p className="mt-6 text-sm text-[var(--muted)]">Keine Dev-Upgrade Einträge gefunden.</p>;
  }
  return (
    <div className="mt-6 overflow-x-auto">
      <table className="w-full text-left text-sm">
        <thead className="text-xs uppercase tracking-[0.2em] text-[var(--muted)]">
          <tr>
            <th className="pb-3">ID</th>
            <th className="pb-3">User</th>
            <th className="pb-3">E-Mail</th>
            <th className="pb-3">Provider</th>
            <th className="pb-3">Betrag</th>
            <th className="pb-3">Status</th>
            <th className="pb-3">Bezahlt</th>
            <th className="pb-3">Verbraucht</th>
            <th className="pb-3">Ref</th>
          </tr>
        </thead>
        <tbody className="text-[var(--ink)]">
          {payments.map((payment) => (
            <tr key={payment.id} className="border-t border-[var(--stroke)]">
              <td className="py-3">{payment.id}</td>
              <td className="py-3">{payment.user_id}</td>
              <td className="py-3">{payment.user_email || "-"}</td>
              <td className="py-3">{payment.provider || "-"}</td>
              <td className="py-3">
                {Number(payment.amount || 0).toFixed(2)} {payment.currency || "EUR"}
              </td>
              <td className="py-3">
                {payment.is_consumed || payment.consumed_at ? (
                  <span className="rounded-full border border-[var(--stroke)] bg-[var(--bg-soft)] px-2 py-1 text-xs text-[var(--accent)]">
                    consumed
                  </span>
                ) : (
                  <span className="rounded-full border border-[var(--stroke)] bg-[var(--bg-soft)] px-2 py-1 text-xs text-[var(--accent-warm)]">
                    open
                  </span>
                )}
              </td>
              <td className="py-3">{formatTimestamp(payment.paid_at)}</td>
              <td className="py-3">{formatTimestamp(payment.consumed_at || null)}</td>
              <td className="py-3">
                <span className="font-mono text-xs">{payment.payment_ref || "-"}</span>
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
  selectedIds,
  onToggleSelection,
  onSelectAll,
  onClearSection,
  onApprove,
  onReject,
  onManifest,
  onFiles,
  onDownloadZip,
}: {
  submissions: Submission[];
  selectedIds: Set<number>;
  onToggleSelection: (id: number) => void;
  onSelectAll: (ids: number[]) => void;
  onClearSection: (ids: number[]) => void;
  onApprove: (submission: Submission) => void;
  onReject: (submission: Submission) => void;
  onManifest: (submission: Submission) => void;
  onFiles: (submission: Submission) => void;
  onDownloadZip: (submission: Submission) => void;
}) {
  if (!submissions.length) {
    return <p className="mt-6 text-sm text-[var(--muted)]">Keine Anfragen.</p>;
  }
  const pending = submissions.filter((s) => s.status === "pending");
  const approved = submissions.filter((s) => s.status === "approved");
  const rejected = submissions.filter((s) => s.status === "rejected");
  return (
    <div className="mt-6 grid gap-6">
      <SubmissionSection
        title="Offen"
        items={pending}
        tone="pending"
        selectedIds={selectedIds}
        onToggleSelection={onToggleSelection}
        onSelectAll={onSelectAll}
        onClearSection={onClearSection}
        onApprove={onApprove}
        onReject={onReject}
        onManifest={onManifest}
        onFiles={onFiles}
        onDownloadZip={onDownloadZip}
      />
      <SubmissionSection
        title="Approved"
        items={approved}
        tone="approved"
        selectedIds={selectedIds}
        onToggleSelection={onToggleSelection}
        onSelectAll={onSelectAll}
        onClearSection={onClearSection}
        onApprove={onApprove}
        onReject={onReject}
        onManifest={onManifest}
        onFiles={onFiles}
        onDownloadZip={onDownloadZip}
      />
      <SubmissionSection
        title="Rejected"
        items={rejected}
        tone="rejected"
        selectedIds={selectedIds}
        onToggleSelection={onToggleSelection}
        onSelectAll={onSelectAll}
        onClearSection={onClearSection}
        onApprove={onApprove}
        onReject={onReject}
        onManifest={onManifest}
        onFiles={onFiles}
        onDownloadZip={onDownloadZip}
      />
    </div>
  );
}

function SubmissionSection({
  title,
  items,
  tone,
  selectedIds,
  onToggleSelection,
  onSelectAll,
  onClearSection,
  onApprove,
  onReject,
  onManifest,
  onFiles,
  onDownloadZip,
}: {
  title: string;
  items: Submission[];
  tone: "pending" | "approved" | "rejected";
  selectedIds: Set<number>;
  onToggleSelection: (id: number) => void;
  onSelectAll: (ids: number[]) => void;
  onClearSection: (ids: number[]) => void;
  onApprove: (submission: Submission) => void;
  onReject: (submission: Submission) => void;
  onManifest: (submission: Submission) => void;
  onFiles: (submission: Submission) => void;
  onDownloadZip: (submission: Submission) => void;
}) {
  const ids = items.map((item) => item.id);
  const selectedCount = ids.filter((id) => selectedIds.has(id)).length;
  const oldest = items.reduce<string | null>((acc, item) => {
    if (!item.created_at) return acc;
    if (!acc) return item.created_at;
    const accTime = new Date(acc).getTime();
    const itemTime = new Date(item.created_at).getTime();
    return itemTime < accTime ? item.created_at : acc;
  }, null);
  const warnCount = items.filter(
    (item) => submissionAgeTone(item.created_at) === "warn"
  ).length;
  const critCount = items.filter(
    (item) => submissionAgeTone(item.created_at) === "crit"
  ).length;
  return (
    <section className="space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm uppercase tracking-[0.3em] text-[var(--muted)]">
          {title}
        </h3>
        <div className="flex flex-wrap items-center gap-2 text-xs text-[var(--muted)]">
          <span>{items.length}</span>
          {oldest ? (
            <span className="rounded-full border border-[var(--stroke)] px-2 py-1 text-[10px] uppercase tracking-[0.2em] text-[var(--muted)]">
              Älteste: {formatAge(oldest)}
            </span>
          ) : null}
          {tone === "pending" && (warnCount || critCount) ? (
            <span className="rounded-full border border-[var(--stroke)] px-2 py-1 text-[10px] uppercase tracking-[0.2em] text-[var(--muted)]">
              SLA:{" "}
              <span className="text-[var(--accent-warm)]">{warnCount} warn</span>{" "}
              · <span className="text-[var(--danger)]">{critCount} krit</span>
            </span>
          ) : null}
          {items.length ? (
            <>
              <button
                onClick={() => onSelectAll(ids)}
                className="rounded-full border border-[var(--stroke)] px-2 py-1 text-[10px] uppercase tracking-[0.2em] text-[var(--muted)] hover:border-[var(--accent)]"
              >
                Alle auswählen
              </button>
              <button
                onClick={() => onClearSection(ids)}
                className="rounded-full border border-[var(--stroke)] px-2 py-1 text-[10px] uppercase tracking-[0.2em] text-[var(--muted)] hover:border-[var(--accent)]"
              >
                Auswahl löschen
              </button>
              <span className="text-[10px] uppercase tracking-[0.2em] text-[var(--muted)]">
                {selectedCount} markiert
              </span>
            </>
          ) : null}
        </div>
      </div>
      {items.length === 0 ? (
        <p className="text-sm text-[var(--muted)]">Keine Einträge.</p>
      ) : (
        <div className="grid gap-4">
          {items.map((submission) => (
            <div
              key={submission.id}
              className={`rounded-2xl border border-[var(--stroke)] bg-[var(--bg-soft)] p-4 ${
                selectedIds.has(submission.id)
                  ? "ring-1 ring-[var(--accent)]/40"
                  : ""
              }`}
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
                  {submission.created_at ? (
                    <p className="mt-1 text-xs text-[var(--muted)]">
                      Eingereicht:{" "}
                      <span className="text-[var(--ink)]">
                        {formatTimestamp(submission.created_at)}
                      </span>{" "}
                      · vor {formatAge(submission.created_at)}
                    </p>
                  ) : null}
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  {tone === "pending" && submission.created_at ? (
                    <span
                      className={`rounded-full px-3 py-1 text-[10px] uppercase tracking-[0.2em] ${
                        submissionAgeTone(submission.created_at) === "crit"
                          ? "bg-[rgba(255,107,107,0.15)] text-[var(--danger)]"
                          : submissionAgeTone(submission.created_at) === "warn"
                          ? "bg-[rgba(240,198,107,0.2)] text-[var(--accent-warm)]"
                          : "border border-[var(--stroke)] text-[var(--muted)]"
                      }`}
                    >
                      SLA {formatAge(submission.created_at)}
                    </span>
                  ) : null}
                  <span
                    className={`rounded-full px-3 py-1 text-xs uppercase tracking-[0.2em] ${
                      tone === "pending"
                        ? "bg-[rgba(128,240,184,0.15)] text-[var(--accent)]"
                        : tone === "approved"
                        ? "bg-[rgba(90,212,255,0.15)] text-[var(--accent-2)]"
                        : "bg-[rgba(255,107,107,0.15)] text-[var(--danger)]"
                    }`}
                  >
                    {submission.status}
                  </span>
                </div>
              </div>
              <div className="mt-4 flex flex-wrap items-center gap-2">
                <label className="flex items-center gap-2 text-xs text-[var(--muted)]">
                  <input
                    type="checkbox"
                    checked={selectedIds.has(submission.id)}
                    onChange={() => onToggleSelection(submission.id)}
                    className="h-4 w-4 accent-[var(--accent)]"
                  />
                  Auswahl
                </label>
                <button
                  onClick={() => onManifest(submission)}
                  className="rounded-full border border-[var(--stroke)] px-3 py-1 text-xs text-[var(--muted)] hover:border-[var(--accent)]"
                >
                  Manifest
                </button>
                <button
                  onClick={() => onFiles(submission)}
                  className="rounded-full border border-[var(--stroke)] px-3 py-1 text-xs text-[var(--muted)] hover:border-[var(--accent)]"
                >
                  Dateien
                </button>
                <button
                  onClick={() => onDownloadZip(submission)}
                  className="rounded-full border border-[var(--stroke)] px-3 py-1 text-xs text-[var(--muted)] hover:border-[var(--accent)]"
                >
                  Download ZIP
                </button>
                <button
                  onClick={() => navigator.clipboard.writeText(submission.app_slug)}
                  className="rounded-full border border-[var(--stroke)] px-3 py-1 text-xs text-[var(--muted)] hover:border-[var(--accent)]"
                >
                  Copy Slug
                </button>
                <button
                  onClick={() =>
                    navigator.clipboard.writeText(
                      `${submission.app_slug}@${submission.version} (${submission.platform}/${submission.channel})`
                    )
                  }
                  className="rounded-full border border-[var(--stroke)] px-3 py-1 text-xs text-[var(--muted)] hover:border-[var(--accent)]"
                >
                  Copy Summary
                </button>
                <button
                  onClick={() => navigator.clipboard.writeText(submission.version)}
                  className="rounded-full border border-[var(--stroke)] px-3 py-1 text-xs text-[var(--muted)] hover:border-[var(--accent)]"
                >
                  Copy Version
                </button>
                {submission.note ? (
                  <span className="rounded-full border border-[var(--stroke)] bg-[var(--bg-soft)] px-3 py-1 text-xs text-[var(--muted)]">
                    {submission.note}
                  </span>
                ) : null}
                {tone !== "approved" ? (
                  <button
                    onClick={() => onApprove(submission)}
                    className="rounded-full bg-[var(--accent)] px-3 py-1 text-xs font-semibold text-black"
                  >
                    Approve
                  </button>
                ) : null}
                {tone !== "rejected" ? (
                  <button
                    onClick={() => onReject(submission)}
                    className="rounded-full border border-[var(--danger)]/50 px-3 py-1 text-xs text-[var(--danger)]"
                  >
                    Reject
                  </button>
                ) : null}
              </div>
            </div>
          ))}
        </div>
      )}
    </section>
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
          <div className="flex items-center justify-between gap-3">
            <p className="text-sm font-semibold text-[var(--ink)]">{game.title}</p>
            {game.sale_percent > 0 ? (
              <span className="rounded-full bg-[rgba(128,240,184,0.2)] px-2 py-1 text-xs text-[var(--accent)]">
                -{game.sale_percent}%
              </span>
            ) : null}
          </div>
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

function formatCurrency(value: number) {
  return new Intl.NumberFormat("de-DE", {
    style: "currency",
    currency: "EUR",
    minimumFractionDigits: 2,
  }).format(value || 0);
}

function formatTimestamp(ts?: string | null) {
  if (!ts) return "—";
  const parsed = new Date(ts);
  if (Number.isNaN(parsed.getTime())) return ts;
  return parsed.toLocaleString("de-DE", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatAge(ts?: string | null) {
  if (!ts) return "—";
  const parsed = new Date(ts);
  const time = parsed.getTime();
  if (Number.isNaN(time)) return "—";
  const diff = Date.now() - time;
  if (diff < 0) return "—";
  const minutes = Math.floor(diff / 60000);
  if (minutes < 60) return `${minutes}m`;
  const hours = Math.floor(minutes / 60);
  if (hours < 48) return `${hours}h`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days}d`;
  const months = Math.floor(days / 30);
  if (months < 12) return `${months}mo`;
  const years = Math.floor(months / 12);
  return `${years}y`;
}

function submissionAgeTone(ts?: string | null) {
  if (!ts) return "ok";
  const parsed = new Date(ts);
  const time = parsed.getTime();
  if (Number.isNaN(time)) return "ok";
  const diffHours = (Date.now() - time) / 3600000;
  if (diffHours >= 72) return "crit";
  if (diffHours >= 24) return "warn";
  return "ok";
}

function formatBytes(bytes?: number) {
  if (!bytes) return "0 B";
  const sizes = ["B", "KB", "MB", "GB"];
  const i = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), sizes.length - 1);
  return `${(bytes / Math.pow(1024, i)).toFixed(1)} ${sizes[i]}`;
}

function shortHash(hash: string) {
  if (hash.length <= 12) return hash;
  return `${hash.slice(0, 8)}…${hash.slice(-4)}`;
}
