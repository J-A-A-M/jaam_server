import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Server, CheckCircle2, XCircle, Plus, Pencil, Trash2, FlaskConical, ToggleLeft, ToggleRight } from "lucide-react";
import { api, type RedisServerConfig, type RedisServerConfigInput } from "@/lib/api";
import { useAuth } from "@/components/AuthContext";
import { Badge, Button, Card, CardBody, Input, Modal, Spinner } from "@/components/ui";
import { fmtDateTime } from "@/lib/utils";

const EMPTY_FORM: RedisServerConfigInput = { name: "", host: "", port: 6379, db: 0, password: undefined, enabled: true };

function ConfigSection() {
  const qc = useQueryClient();
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<RedisServerConfig | null>(null);
  const [form, setForm] = useState<RedisServerConfigInput>(EMPTY_FORM);
  const [changePassword, setChangePassword] = useState(false);
  const [error, setError] = useState("");
  const [testResults, setTestResults] = useState<Record<number, { ok: boolean; online: number } | "loading">>({});

  const { data: configs, isLoading } = useQuery({
    queryKey: ["server-configs"],
    queryFn: api.serverConfigs,
  });

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["server-configs"] });
    qc.invalidateQueries({ queryKey: ["servers"] });
  };

  const createMut = useMutation({
    mutationFn: (body: RedisServerConfigInput) => api.createServerConfig(body),
    onSuccess: () => { invalidate(); closeModal(); },
    onError: (e: Error) => setError(e.message),
  });

  const updateMut = useMutation({
    mutationFn: ({ id, body }: { id: number; body: object }) => api.updateServerConfig(id, body),
    onSuccess: () => { invalidate(); closeModal(); },
    onError: (e: Error) => setError(e.message),
  });

  const deleteMut = useMutation({
    mutationFn: (id: number) => api.deleteServerConfig(id),
    onSuccess: invalidate,
    onError: (e: Error) => alert(e.message),
  });

  const openCreate = () => {
    setEditing(null);
    setForm(EMPTY_FORM);
    setChangePassword(false);
    setError("");
    setModalOpen(true);
  };

  const openEdit = (cfg: RedisServerConfig) => {
    setEditing(cfg);
    setForm({ name: cfg.name, host: cfg.host, port: cfg.port, db: cfg.db, password: undefined, enabled: cfg.enabled });
    setChangePassword(false);
    setError("");
    setModalOpen(true);
  };

  const closeModal = () => { setModalOpen(false); setEditing(null); setError(""); };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.name.trim() || !form.host.trim()) { setError("Назва і хост обов'язкові"); return; }
    if (editing) {
      const body: Record<string, unknown> = {
        name: form.name, host: form.host, port: form.port, db: form.db, enabled: form.enabled,
      };
      if (changePassword) body.password = form.password || null;
      updateMut.mutate({ id: editing.id, body });
    } else {
      createMut.mutate({ ...form, password: form.password || null });
    }
  };

  const handleTest = async (id: number) => {
    setTestResults(prev => ({ ...prev, [id]: "loading" }));
    try {
      const res = await api.testServerConfig(id);
      setTestResults(prev => ({ ...prev, [id]: { ok: res.ok, online: res.online } }));
    } catch {
      setTestResults(prev => ({ ...prev, [id]: { ok: false, online: 0 } }));
    }
  };

  return (
    <>
      <div className="flex items-end justify-between">
        <div>
          <h2 className="text-base font-semibold text-foreground">Конфігурація</h2>
          <p className="text-sm text-muted-foreground">Підключення до Redis-інстансів</p>
        </div>
        <Button onClick={openCreate} className="shrink-0">
          <Plus className="h-4 w-4" /> <span className="hidden sm:inline">Додати</span>
        </Button>
      </div>

      <Card className="overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border/[0.1] text-left text-xs uppercase tracking-wide text-muted-foreground">
                <th className="px-3 py-3 font-medium sm:px-4">Назва</th>
                <th className="px-3 py-3 font-medium sm:px-4">Хост : порт</th>
                <th className="hidden px-4 py-3 font-medium sm:table-cell">DB</th>
                <th className="hidden px-4 py-3 font-medium lg:table-cell">Пароль</th>
                <th className="px-3 py-3 font-medium sm:px-4">Стан</th>
                <th className="px-3 py-3 sm:px-4"></th>
              </tr>
            </thead>
            <tbody>
              {isLoading ? (
                <tr><td colSpan={6} className="py-16 text-center"><Spinner className="mx-auto h-6 w-6" /></td></tr>
              ) : configs?.length === 0 ? (
                <tr><td colSpan={6} className="py-10 text-center text-sm text-muted-foreground">Немає конфігурацій</td></tr>
              ) : configs?.map((cfg) => {
                const testRes = testResults[cfg.id];
                return (
                  <tr key={cfg.id} className="border-b border-border/[0.07] transition hover:bg-muted/40">
                    <td className="px-3 py-3 font-medium text-foreground sm:px-4">{cfg.name}</td>
                    <td className="px-3 py-3 font-mono text-xs text-muted-foreground sm:px-4">
                      {cfg.host}:{cfg.port}
                    </td>
                    <td className="hidden px-4 py-3 font-mono text-xs text-muted-foreground sm:table-cell">{cfg.db}</td>
                    <td className="hidden px-4 py-3 lg:table-cell">
                      {cfg.has_password
                        ? <span className="font-mono text-xs text-muted-foreground">••••••</span>
                        : <span className="text-xs text-muted-foreground/50">—</span>}
                    </td>
                    <td className="px-3 py-3 sm:px-4">
                      <div className="flex items-center gap-2">
                        <Badge variant={cfg.enabled ? "online" : "muted"}>
                          {cfg.enabled ? "увімк." : "вимк."}
                        </Badge>
                        {testRes === "loading" && <Spinner className="h-3.5 w-3.5" />}
                        {testRes && testRes !== "loading" && (
                          testRes.ok
                            ? <CheckCircle2 className="h-3.5 w-3.5 text-success" />
                            : <XCircle className="h-3.5 w-3.5 text-danger" />
                        )}
                      </div>
                    </td>
                    <td className="px-3 py-3 sm:px-4">
                      <div className="flex items-center justify-end gap-1">
                        <button
                          onClick={() => handleTest(cfg.id)}
                          disabled={testRes === "loading"}
                          className="rounded-md p-1.5 text-muted-foreground transition hover:bg-muted hover:text-foreground disabled:opacity-40"
                          title="Тест з'єднання"
                        >
                          <FlaskConical className="h-4 w-4" />
                        </button>
                        <button
                          onClick={() => openEdit(cfg)}
                          className="rounded-md p-1.5 text-muted-foreground transition hover:bg-muted hover:text-foreground"
                          title="Редагувати"
                        >
                          <Pencil className="h-4 w-4" />
                        </button>
                        <button
                          onClick={() => { if (confirm(`Видалити сервер «${cfg.name}»?`)) deleteMut.mutate(cfg.id); }}
                          disabled={deleteMut.isPending}
                          className="rounded-md p-1.5 text-muted-foreground transition hover:bg-danger/15 hover:text-danger disabled:opacity-40"
                          title="Видалити"
                        >
                          <Trash2 className="h-4 w-4" />
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </Card>

      <Modal open={modalOpen} onClose={closeModal} title={editing ? `Редагувати: ${editing.name}` : "Новий Redis-сервер"}>
        <form onSubmit={handleSubmit} className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div className="col-span-2">
              <label className="mb-1 block text-xs text-muted-foreground">Назва *</label>
              <Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="напр. Server 1" autoFocus required />
            </div>
            <div>
              <label className="mb-1 block text-xs text-muted-foreground">Хост *</label>
              <Input value={form.host} onChange={(e) => setForm({ ...form, host: e.target.value })} placeholder="redis або 10.0.0.1" required />
            </div>
            <div>
              <label className="mb-1 block text-xs text-muted-foreground">Порт</label>
              <Input type="number" value={form.port} onChange={(e) => setForm({ ...form, port: Number(e.target.value) })} min={1} max={65535} />
            </div>
            <div>
              <label className="mb-1 block text-xs text-muted-foreground">DB</label>
              <Input type="number" value={form.db} onChange={(e) => setForm({ ...form, db: Number(e.target.value) })} min={0} max={15} />
            </div>
            <div className="flex items-end pb-0.5">
              <button
                type="button"
                onClick={() => setForm({ ...form, enabled: !form.enabled })}
                className="flex items-center gap-2 text-sm text-foreground"
              >
                {form.enabled
                  ? <ToggleRight className="h-5 w-5 text-primary" />
                  : <ToggleLeft className="h-5 w-5 text-muted-foreground" />}
                {form.enabled ? "Увімкнено" : "Вимкнено"}
              </button>
            </div>
          </div>

          {editing ? (
            <div>
              <label className="mb-2 flex cursor-pointer items-center gap-2 text-xs text-muted-foreground">
                <input type="checkbox" checked={changePassword} onChange={(e) => setChangePassword(e.target.checked)} className="h-3.5 w-3.5" />
                Змінити пароль {editing.has_password ? "(зараз встановлений)" : "(зараз не встановлений)"}
              </label>
              {changePassword && (
                <Input
                  type="password"
                  value={form.password ?? ""}
                  onChange={(e) => setForm({ ...form, password: e.target.value })}
                  placeholder="Новий пароль (порожньо — без пароля)"
                />
              )}
            </div>
          ) : (
            <div>
              <label className="mb-1 block text-xs text-muted-foreground">Пароль</label>
              <Input
                type="password"
                value={form.password ?? ""}
                onChange={(e) => setForm({ ...form, password: e.target.value })}
                placeholder="Залиште порожнім, якщо без пароля"
              />
            </div>
          )}

          {error && <div className="text-sm text-danger">{error}</div>}

          <div className="flex justify-end gap-2 pt-1">
            <button type="button" onClick={closeModal} className="rounded border border-border/[0.1] px-4 py-2 text-sm transition hover:bg-muted hover:text-foreground">
              Скасувати
            </button>
            <Button type="submit" disabled={createMut.isPending || updateMut.isPending}>
              {(createMut.isPending || updateMut.isPending) ? <Spinner /> : editing ? "Зберегти" : "Створити"}
            </Button>
          </div>
        </form>
      </Modal>
    </>
  );
}

export default function Servers() {
  const { user } = useAuth();
  const { data, isLoading } = useQuery({
    queryKey: ["servers"],
    queryFn: api.servers,
    refetchInterval: 10000,
  });

  return (
    <div className="space-y-6 p-4 sm:p-6">
      <div>
        <h1 className="text-xl font-bold sm:text-2xl">Сервери</h1>
        <p className="text-sm text-muted-foreground">Стан Redis-інстансів та кількість клієнтів</p>
      </div>

      {isLoading || !data ? (
        <div className="flex justify-center py-20"><Spinner className="h-8 w-8" /></div>
      ) : data.length === 0 ? (
        <Card><CardBody className="py-12 text-center text-sm text-muted-foreground">Немає активних серверів</CardBody></Card>
      ) : (
        <div className="grid gap-3 sm:gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {data.map((s) => (
            <Card key={s.name}>
              <CardBody className="pt-5">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Server className="h-5 w-5 text-muted-foreground" />
                    <span className="font-mono text-sm text-foreground">{s.name}</span>
                  </div>
                  {s.ok
                    ? <CheckCircle2 className="h-5 w-5 text-success" />
                    : <XCircle className="h-5 w-5 text-danger" />}
                </div>
                <div className="mt-4 font-mono text-3xl font-bold text-primary">{s.ok ? s.online : "—"}</div>
                <div className="text-xs text-muted-foreground">мап онлайн</div>
                <div className="mt-3 text-xs text-muted-foreground">
                  {s.ok ? <span className="text-success">доступний</span> : <span className="text-danger">недоступний</span>}
                  {" · "}перевірено {fmtDateTime(s.checked_at)}
                </div>
              </CardBody>
            </Card>
          ))}
        </div>
      )}

      {user?.role === "admin" && <ConfigSection />}
    </div>
  );
}
