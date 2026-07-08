import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Trash2, Shield, Eye, KeyRound } from "lucide-react";
import { startRegistration } from "@simplewebauthn/browser";
import { api, type PanelUserInput } from "@/lib/api";
import { useAuth } from "@/components/AuthContext";
import { Badge, Button, Card, Input, Modal, RelativeTime, Select, Spinner } from "@/components/ui";
import { fmtDateTime } from "@/lib/utils";

const EMPTY: PanelUserInput = { username: "", password: "", role: "admin" };

function PasskeysSection() {
  const qc = useQueryClient();
  const [addOpen, setAddOpen] = useState(false);
  const [keyName, setKeyName] = useState("");
  const [addError, setAddError] = useState("");
  const [adding, setAdding] = useState(false);

  const { data: creds, isLoading } = useQuery({
    queryKey: ["passkeys"],
    queryFn: api.webauthn.credentials,
  });

  const delMut = useMutation({
    mutationFn: (id: number) => api.webauthn.deleteCredential(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["passkeys"] }),
  });

  const addPasskey = async () => {
    setAddError("");
    setAdding(true);
    try {
      const name = keyName.trim() || "Ключ";
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const options = await api.webauthn.registerBegin(name) as any;
      const credential = await startRegistration({ optionsJSON: options });
      await api.webauthn.registerComplete(credential);
      qc.invalidateQueries({ queryKey: ["passkeys"] });
      setAddOpen(false);
      setKeyName("");
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      if (!msg.includes("cancel") && !msg.includes("abort") && !msg.includes("NotAllowed")) {
        setAddError("Не вдалося додати ключ: " + msg);
      }
    } finally {
      setAdding(false);
    }
  };

  return (
    <Card className="overflow-hidden">
      <div className="flex items-center justify-between border-b border-border/[0.07] px-4 py-3 sm:px-5">
        <div className="flex items-center gap-2 text-sm font-medium text-foreground">
          <KeyRound className="h-4 w-4 text-muted-foreground" />
          Мої ключі доступу (Passkeys)
        </div>
        <button
          onClick={() => { setKeyName(""); setAddError(""); setAddOpen(true); }}
          className="flex items-center gap-1.5 rounded border border-border/[0.15] px-2.5 py-1.5 text-xs text-muted-foreground transition hover:border-primary/40 hover:text-foreground"
        >
          <Plus className="h-3.5 w-3.5" /> Додати
        </button>
      </div>

      {isLoading ? (
        <div className="flex justify-center py-6"><Spinner className="h-5 w-5" /></div>
      ) : creds && creds.length > 0 ? (
        <div className="divide-y divide-border/[0.07]">
          {creds.map((c) => (
            <div key={c.id} className="flex items-center justify-between px-4 py-3 sm:px-5">
              <div>
                <div className="text-sm text-foreground">{c.name}</div>
                <div className="mt-0.5 text-xs text-muted-foreground">
                  Додано <RelativeTime ts={c.created_at} />
                  {c.last_used_at && <> · Використано <RelativeTime ts={c.last_used_at} /></>}
                </div>
              </div>
              <button
                onClick={() => { if (confirm(`Видалити ключ «${c.name}»?`)) delMut.mutate(c.id); }}
                disabled={delMut.isPending}
                className="rounded-md p-1.5 text-muted-foreground transition hover:bg-danger/15 hover:text-danger disabled:opacity-40"
                title="Видалити ключ"
              >
                <Trash2 className="h-4 w-4" />
              </button>
            </div>
          ))}
        </div>
      ) : (
        <div className="px-4 py-6 text-center text-sm text-muted-foreground sm:px-5">
          Ключів поки немає — додайте, щоб входити без пароля
        </div>
      )}

      <Modal open={addOpen} onClose={() => setAddOpen(false)} title="Новий ключ доступу">
        <div className="space-y-3">
          <div>
            <label className="mb-1 block text-xs text-muted-foreground">Назва ключа</label>
            <Input
              value={keyName}
              onChange={(e) => setKeyName(e.target.value)}
              placeholder="напр. MacBook Touch ID"
              autoFocus
            />
          </div>
          <p className="text-xs text-muted-foreground">
            Після натискання «Зареєструвати» браузер попросить підтвердити особу через Touch ID, Face ID або ключ безпеки.
          </p>
          {addError && <div className="text-sm text-danger">{addError}</div>}
          <div className="flex justify-end gap-2 pt-1">
            <button type="button" onClick={() => setAddOpen(false)} className="rounded border border-border/[0.1] px-4 py-2 text-sm transition hover:bg-muted hover:text-foreground">
              Скасувати
            </button>
            <Button onClick={addPasskey} disabled={adding}>
              {adding ? <Spinner /> : "Зареєструвати"}
            </Button>
          </div>
        </div>
      </Modal>
    </Card>
  );
}

export default function Users() {
  const qc = useQueryClient();
  const { user } = useAuth();
  const [modalOpen, setModalOpen] = useState(false);
  const [form, setForm] = useState<PanelUserInput>(EMPTY);
  const [error, setError] = useState("");

  const { data, isLoading } = useQuery({ queryKey: ["users"], queryFn: api.users });
  const invalidate = () => qc.invalidateQueries({ queryKey: ["users"] });

  const createMut = useMutation({
    mutationFn: (body: PanelUserInput) => api.createUser(body),
    onSuccess: () => { invalidate(); setModalOpen(false); setError(""); },
    onError: (e: Error) => setError(e.message),
  });

  const delMut = useMutation({
    mutationFn: (username: string) => api.deleteUser(username),
    onSuccess: invalidate,
    onError: (e: Error) => alert(e.message),
  });

  return (
    <div className="space-y-4 p-4 sm:p-6">
      <div className="flex items-end justify-between">
        <div>
          <h1 className="text-xl font-bold sm:text-2xl">Користувачі</h1>
          <p className="text-sm text-muted-foreground">Доступ до адмін-панелі</p>
        </div>
        <Button onClick={() => { setForm(EMPTY); setError(""); setModalOpen(true); }} className="shrink-0">
          <Plus className="h-4 w-4" /> <span className="hidden sm:inline">Додати</span>
        </Button>
      </div>

      <Card className="overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border/[0.1] text-left text-xs uppercase tracking-wide text-muted-foreground">
                <th className="px-3 py-3 font-medium sm:px-4">Логін</th>
                <th className="px-3 py-3 font-medium sm:px-4">Роль</th>
                <th className="hidden px-4 py-3 font-medium sm:table-cell">Створено</th>
                <th className="px-3 py-3 sm:px-4"></th>
              </tr>
            </thead>
            <tbody>
              {isLoading ? (
                <tr><td colSpan={4} className="py-16 text-center"><Spinner className="mx-auto h-6 w-6" /></td></tr>
              ) : (
                data?.map((u) => (
                  <tr key={u.id} className="border-b border-border/[0.07] transition hover:bg-muted/40">
                    <td className="px-3 py-3 font-medium text-foreground sm:px-4">
                      {u.username}
                      {u.username === user?.username && <span className="ml-2 text-xs text-muted-foreground">(ви)</span>}
                    </td>
                    <td className="px-3 py-3 sm:px-4">
                      <Badge variant="muted">
                        {u.role === "admin" ? <><Shield className="h-3 w-3" /> admin</> : <><Eye className="h-3 w-3" /> viewer</>}
                      </Badge>
                    </td>
                    <td className="hidden px-4 py-3 text-muted-foreground sm:table-cell">{fmtDateTime(u.created_at)}</td>
                    <td className="px-3 py-3 sm:px-4">
                      <div className="flex justify-end">
                        <button
                          onClick={() => { if (confirm(`Видалити користувача ${u.username}?`)) delMut.mutate(u.username); }}
                          disabled={delMut.isPending || u.username === user?.username}
                          className="rounded-md p-1.5 text-muted-foreground transition hover:bg-danger/15 hover:text-danger disabled:cursor-not-allowed disabled:opacity-40"
                          title={u.username === user?.username ? "Неможливо видалити себе" : "Видалити"}
                        >
                          <Trash2 className="h-4 w-4" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </Card>

      <PasskeysSection />

      <Modal open={modalOpen} onClose={() => setModalOpen(false)} title="Новий користувач">
        <form onSubmit={(e) => { e.preventDefault(); createMut.mutate(form); }} className="space-y-3">
          <div>
            <label className="mb-1 block text-xs text-muted-foreground">Логін *</label>
            <Input value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} required autoFocus />
          </div>
          <div>
            <label className="mb-1 block text-xs text-muted-foreground">Пароль *</label>
            <Input type="password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} required />
          </div>
          <div>
            <label className="mb-1 block text-xs text-muted-foreground">Роль</label>
            <Select value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })} className="w-full">
              <option value="admin">admin — повний доступ</option>
              <option value="viewer">viewer — лише перегляд</option>
            </Select>
          </div>
          {error && <div className="text-sm text-danger">{error}</div>}
          <div className="flex justify-end gap-2 pt-1">
            <button type="button" onClick={() => setModalOpen(false)} className="rounded border border-border/[0.1] px-4 py-2 text-sm transition hover:bg-muted hover:text-foreground">Скасувати</button>
            <Button type="submit" disabled={createMut.isPending}>{createMut.isPending ? <Spinner /> : "Створити"}</Button>
          </div>
        </form>
      </Modal>
    </div>
  );
}
