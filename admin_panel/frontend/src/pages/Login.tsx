import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "@/components/AuthContext";
import { Spinner } from "@/components/ui";

export default function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

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

        {/* Amber separator */}
        <div className="mb-7 flex items-center gap-3">
          <div className="h-px flex-1 bg-white/[0.06]" />
          <div className="h-px w-8 bg-primary/60" />
          <div className="h-px flex-1 bg-white/[0.06]" />
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
              className="w-full border-0 border-b border-white/[0.1] bg-transparent pb-2 text-sm text-foreground outline-none placeholder:text-muted-foreground/50 transition-colors focus:border-primary/70"
            />
          </div>
          <div className="pt-1">
            <input
              type="password"
              placeholder="Пароль"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
              className="w-full border-0 border-b border-white/[0.1] bg-transparent pb-2 text-sm text-foreground outline-none placeholder:text-muted-foreground/50 transition-colors focus:border-primary/70"
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

        {/* Footer */}
        <p className="mt-8 text-center font-mono text-[9px] uppercase tracking-[0.2em] text-muted-foreground/40">
          Обмежений доступ
        </p>
      </div>
    </div>
  );
}
