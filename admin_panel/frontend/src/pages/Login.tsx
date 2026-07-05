import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { startAuthentication } from "@simplewebauthn/browser";
import { useAuth } from "@/components/AuthContext";
import { api } from "@/lib/api";
import { Spinner } from "@/components/ui";

export default function Login() {
  const { login, refresh } = useAuth();
  const navigate = useNavigate();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [passkeyLoading, setPasskeyLoading] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await login(username, password);
      navigate("/");
    } catch {
      setError("Невірний логін або пароль");
    } finally {
      setLoading(false);
    }
  };

  const loginWithPasskey = async () => {
    setError("");
    setPasskeyLoading(true);
    try {
      const { session_id, options } = await api.webauthn.authBegin();
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const credential = await startAuthentication({ optionsJSON: options as any });
      await api.webauthn.authComplete(session_id, credential);
      await refresh();
      navigate("/");
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      if (!msg.includes("cancel") && !msg.includes("abort") && !msg.includes("NotAllowed")) {
        setError("Не вдалося увійти з ключем доступу");
      }
    } finally {
      setPasskeyLoading(false);
    }
  };

  return (
    <div className="login-bg flex min-h-screen items-center justify-center px-4">
      <div className="w-full max-w-[340px] animate-fade-in">
        {/* Logo block */}
        <div className="mb-8 text-center">
          <div className="mb-3 inline-flex h-12 w-12 items-center justify-center rounded-md border border-primary/30 bg-primary/10 shadow-glow">
            {/* Radar SVG */}
            <svg className="h-6 w-6 text-primary" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
              <circle cx="12" cy="12" r="9" />
              <circle cx="12" cy="12" r="5" />
              <circle cx="12" cy="12" r="1.5" fill="currentColor" stroke="none" />
              <line x1="12" y1="3" x2="12" y2="7" />
              <line x1="12" y1="17" x2="12" y2="21" />
              <line x1="3" y1="12" x2="7" y2="12" />
              <line x1="17" y1="12" x2="21" y2="12" />
            </svg>
          </div>
          <h1 className="text-2xl font-extrabold tracking-tight text-foreground">JAAM</h1>
          <p className="mt-0.5 font-mono text-[10px] uppercase tracking-[0.22em] text-muted-foreground">
            Панель моніторингу
          </p>
        </div>

        {/* Separator */}
        <div className="mb-7 flex items-center gap-3">
          <div className="h-px flex-1 bg-border/[0.07]" />
          <div className="h-px w-8 bg-primary/60" />
          <div className="h-px flex-1 bg-border/[0.07]" />
        </div>

        {/* Form */}
        <form onSubmit={submit} className="space-y-3">
          <div>
            <input
              placeholder="Логін"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              autoFocus
              autoComplete="username"
              className="w-full border-0 border-b border-border/[0.15] bg-transparent pb-2 text-sm text-foreground outline-none placeholder:text-muted-foreground/50 transition-colors focus:border-primary/70"
            />
          </div>
          <div className="pt-1">
            <input
              type="password"
              placeholder="Пароль"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
              className="w-full border-0 border-b border-border/[0.15] bg-transparent pb-2 text-sm text-foreground outline-none placeholder:text-muted-foreground/50 transition-colors focus:border-primary/70"
            />
          </div>

          {error && (
            <p className="font-mono text-xs text-danger">{error}</p>
          )}

          <div className="pt-3">
            <button
              type="submit"
              disabled={loading}
              className="flex w-full items-center justify-center gap-2 rounded bg-primary py-2.5 text-sm font-bold text-primary-foreground transition-all duration-150 hover:brightness-110 hover:shadow-glow active:scale-[0.98] disabled:opacity-40"
            >
              {loading ? <Spinner className="h-4 w-4 border-t-primary-foreground" /> : <>Увійти →</>}
            </button>
          </div>
        </form>

        {/* Passkey divider */}
        <div className="my-6 flex items-center gap-3">
          <div className="h-px flex-1 bg-border/[0.07]" />
          <span className="font-mono text-[9px] uppercase tracking-[0.15em] text-muted-foreground/40">або</span>
          <div className="h-px flex-1 bg-border/[0.07]" />
        </div>

        <button
          onClick={loginWithPasskey}
          disabled={passkeyLoading}
          className="flex w-full items-center justify-center gap-2 rounded border border-border/[0.15] py-2.5 text-sm text-muted-foreground transition-all duration-150 hover:border-primary/40 hover:text-foreground active:scale-[0.98] disabled:opacity-40"
        >
          {passkeyLoading ? (
            <Spinner className="h-4 w-4" />
          ) : (
            <>
              {/* Fingerprint icon */}
              <svg className="h-4 w-4 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round">
                <path d="M12 10a2 2 0 0 0-2 2c0 1.02-.1 2.51-.26 4" />
                <path d="M14 13.12c0 2.38 0 6.38-1 8.88" />
                <path d="M17.29 21.02c.12-.6.43-2.3.5-3.02" />
                <path d="M2 12a10 10 0 0 1 18-6" />
                <path d="M2 17c2 2.2 3.9 3 6 3" />
                <path d="M5 12v-.5C5 8.358 7.358 6 10.5 6a5.5 5.5 0 0 1 5.5 5.5v.5" />
                <path d="M8 16a8.37 8.37 0 0 1-.34-2" />
                <path d="M20 13.5c0 4.46-1.95 7.5-5 8" />
                <path d="M20 9a1 1 0 0 1 0-2" />
              </svg>
              Увійти з ключем доступу
            </>
          )}
        </button>

        {/* Footer */}
        <p className="mt-8 text-center font-mono text-[9px] uppercase tracking-[0.2em] text-muted-foreground/40">
          Обмежений доступ
        </p>
      </div>
    </div>
  );
}
