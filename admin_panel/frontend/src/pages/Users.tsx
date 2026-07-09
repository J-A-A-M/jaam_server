import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Trash2, Shield, Eye, Pencil } from "lucide-react";
import { api, type PanelUser, type PanelUserInput } from "@/lib/api";
import { useAuth } from "@/components/AuthContext";
import { Badge, Button, Card, Input, Modal, Select, Spinner } from "@/components/ui";
import { fmtDateTime } from "@/lib/utils";

const EMPTY: PanelUserInput = { username: "", password: "", role: "admin" };

export default function Users() {
  const qc = useQueryClient();
  const { user } = useAuth();
  const [modalOpen, setModalOpen] = useState(false);
  const [form, setForm] = useState<PanelUserInput>(EMPTY);
  const [error, setError] = useState("");

  // Редагування наявного користувача
  const [editUser, setEditUser] = useState<PanelUser | null>(null);
  const [editRole, setEditRole] = useState("admin");
  const [editPassword, setEditPassword] = useState("");
  const [editError, setEditError] = useState("");

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

  const editMut = useMutation({
    mutationFn: ({ username, role, password }: { username: string; role: string; password?: string }) =>
      api.updateUser(username, { role, ...(password ? { password } : {}) }),
    onSuccess: () => { invalidate(); setEditUser(null); setEditError(""); },
    onError: (e: Error) => setEditError(e.message),
  });

  const openEdit = (u: PanelUser) => {
    setEditUser(u);
    setEditRole(u.role);
    setEditPassword("");
    setEditError("");
  };

  const submitEdit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!editUser) return;
    if (editPassword && editPassword.length < 8) {
      setEditError("Пароль має бути не коротшим за 8 символів");
      return;
    }
    editMut.mutate({ username: editUser.username, role: editRole, password: editPassword || undefined });
  };

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
                      <div className="flex justify-end gap-1">
                        <button
                          onClick={() => openEdit(u)}
                          className="rounded-md p-1.5 text-muted-foreground transition hover:bg-muted hover:text-foreground"
                          title="Редагувати роль / скинути пароль"
                        >
                          <Pencil className="h-4 w-4" />
                        </button>
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

      <Modal open={editUser !== null} onClose={() => setEditUser(null)} title={editUser ? `Редагувати ${editUser.username}` : ""}>
        <form onSubmit={submitEdit} className="space-y-3">
          <div>
            <label className="mb-1 block text-xs text-muted-foreground">Роль</label>
            <Select value={editRole} onChange={(e) => setEditRole(e.target.value)} className="w-full">
              <option value="admin">admin — повний доступ</option>
              <option value="viewer">viewer — лише перегляд</option>
            </Select>
          </div>
          <div>
            <label className="mb-1 block text-xs text-muted-foreground">Новий пароль</label>
            <Input
              type="password"
              value={editPassword}
              onChange={(e) => setEditPassword(e.target.value)}
              placeholder="Залишіть порожнім, щоб не змінювати"
              autoComplete="new-password"
            />
          </div>
          <p className="text-xs text-muted-foreground">
            Зміна ролі чи пароля завершує всі активні сесії цього користувача.
          </p>
          {editError && <div className="text-sm text-danger">{editError}</div>}
          <div className="flex justify-end gap-2 pt-1">
            <button type="button" onClick={() => setEditUser(null)} className="rounded border border-border/[0.1] px-4 py-2 text-sm transition hover:bg-muted hover:text-foreground">Скасувати</button>
            <Button type="submit" disabled={editMut.isPending}>{editMut.isPending ? <Spinner /> : "Зберегти"}</Button>
          </div>
        </form>
      </Modal>
    </div>
  );
}
