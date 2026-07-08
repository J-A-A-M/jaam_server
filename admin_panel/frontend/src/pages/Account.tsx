import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Trash2, KeyRound, Lock } from "lucide-react";
import { startRegistration } from "@simplewebauthn/browser";
import { api } from "@/lib/api";
import { Button, Card, Input, Modal, RelativeTime, Spinner } from "@/components/ui";

function ChangePasswordSection() {
  const [oldPw, setOldPw] = useState("");
  const [newPw, setNewPw] = useState("");
  const [confirmPw, setConfirmPw] = useState("");
  const [error, setError] = useState("");
  const [ok, setOk] = useState(false);

  const mut = useMutation({
    mutationFn: () => api.changeOwnPassword(oldPw, newPw),
    onSuccess: () => {
      setOk(true);
      setError("");
      setOldPw("");
      setNewPw("");
      setConfirmPw("");
    },
    onError: (e: Error) => {
      setError(e.message);
      setOk(false);
    },
  });

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setOk(false);
    if (newPw.length < 8) {
      setError("Новий пароль має бути не коротшим за 8 символів");
      return;
    }
    if (newPw !== confirmPw) {
      setError("Паролі не збігаються");
      return;
    }
    mut.mutate();
  };

  return (
    <Card className="overflow-hidden">
      <div className="flex items-center gap-2 border-b border-border/[0.07] px-4 py-3 text-sm font-medium text-foreground sm:px-5">
        <Lock className="h-4 w-4 text-muted-foreground" />
        Мій пароль
      </div>
      <form onSubmit={submit} className="space-y-3 p-4 sm:p-5">
        <div>
          <label className="mb-1 block text-xs text-muted-foreground">Поточний пароль</label>
          <Input type="password" value={oldPw} onChange={(e) => setOldPw(e.target.value)} required autoComplete="current-password" />
        </div>
        <div>
          <label className="mb-1 block text-xs text-muted-foreground">Новий пароль</label>
          <Input type="password" value={newPw} onChange={(e) => setNewPw(e.target.value)} required autoComplete="new-password" />
        </div>
        <div>
          <label className="mb-1 block text-xs text-muted-foreground">Повторіть новий пароль</label>
          <Input type="password" value={confirmPw} onChange={(e) => setConfirmPw(e.target.value)} required autoComplete="new-password" />
        </div>
        <p className="text-xs text-muted-foreground">
          Після зміни пароля всі інші активні сесії буде завершено. Поточна сесія залишиться активною.
        </p>
        {error && <div className="text-sm text-danger">{error}</div>}
        {ok && <div className="text-sm text-emerald-500">Пароль змінено.</div>}
        <div className="flex justify-end pt-1">
          <Button type="submit" disabled={mut.isPending}>{mut.isPending ? <Spinner /> : "Змінити пароль"}</Button>
        </div>
      </form>
    </Card>
  );
}

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

export default function Account() {
  return (
    <div className="space-y-4 p-4 sm:space-y-6 sm:p-6">
      <div>
        <h1 className="text-xl font-bold sm:text-2xl">Акаунт</h1>
        <p className="text-sm text-muted-foreground">Пароль і ключі доступу</p>
      </div>
      <div className="grid gap-4 sm:gap-6 lg:grid-cols-2">
        <ChangePasswordSection />
        <PasskeysSection />
      </div>
    </div>
  );
}
