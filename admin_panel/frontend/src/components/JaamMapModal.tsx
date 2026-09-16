import React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type ClaimCodeResult, type JaamMap, type JaamMapInput, type ProvisionResult } from "@/lib/api";
import { Badge, Button, Input, Modal, Select, Spinner, Textarea } from "@/components/ui";
import { useAuth } from "@/components/AuthContext";

// Модалка редагує запис реєстру. Приймаємо і повний JaamMap (сторінка «Реєстр»),
// і Device (сторінка мапи) — потрібні лише ці поля; is_prototype у Device може бути null.
export type JaamMapEditable = Pick<
  JaamMap,
  "chip_id" | "map_id" | "hw_version" | "order_number" | "customer_info" | "secret_version" | "whitelisted"
> & { is_prototype: boolean | null };

export interface JaamMapModalProps {
  open: boolean;
  onClose: () => void;
  editing?: JaamMapEditable | null;
  defaultChipId?: string;
  onSuccess?: () => void;
}

export function JaamMapModal({ open, onClose, editing, defaultChipId, onSuccess }: JaamMapModalProps) {
  const qc = useQueryClient();
  const { user } = useAuth();
  const { data: hwVersions } = useQuery({ queryKey: ["hw-versions"], queryFn: api.hwVersions, enabled: open });
  const empty: JaamMapInput = { chip_id: "", map_id: "", hw_version: hwVersions?.[0]?.name ?? "", is_prototype: false, order_number: "", customer_info: "" };

  const [form, setForm] = React.useState<JaamMapInput>(empty);
  const [error, setError] = React.useState("");
  // Секрет повертається лише один раз, одразу у відповіді на provision — сервер його ніде
  // не зберігає, тож показуємо саме цей результат, поки модалка не закриється/не перезайде.
  const [provisioned, setProvisioned] = React.useState<ProvisionResult | null>(null);
  // Так само одноразовий - показується лише в цій відповіді, ніде на сервері не зберігається
  // (лише SHA-256 хеш у Redis з TTL). Незалежний від provisioned - адмін бачить, який саме
  // з двох щойно видав.
  const [claimed, setClaimed] = React.useState<ClaimCodeResult | null>(null);
  const [whitelisted, setWhitelisted] = React.useState(true);
  const [secretVersion, setSecretVersion] = React.useState(0);

  React.useEffect(() => {
    if (editing) {
      setForm({
        chip_id: editing.chip_id,
        map_id: editing.map_id ?? "",
        hw_version: editing.hw_version ?? "",
        is_prototype: editing.is_prototype ?? false,
        order_number: editing.order_number ?? "",
        customer_info: editing.customer_info ?? "",
      });
      setWhitelisted(editing.whitelisted);
      setSecretVersion(editing.secret_version);
    } else {
      setForm({ ...empty, chip_id: defaultChipId || "" });
      setWhitelisted(true);
      setSecretVersion(0);
    }
    setProvisioned(null);
    setClaimed(null);
    setError("");
  }, [editing, defaultChipId, open]);

  const provisionMut = useMutation({
    mutationFn: () => api.provisionDevice(editing!.chip_id),
    onSuccess: (res) => {
      setProvisioned(res);
      setClaimed(null);
      setWhitelisted(res.whitelisted);
      setSecretVersion(res.secret_version);
      qc.invalidateQueries({ queryKey: ["inventory"] });
      qc.invalidateQueries({ queryKey: ["device"] });
    },
    onError: (e: Error) => setError(e.message),
  });

  const claimCodeMut = useMutation({
    mutationFn: () => api.issueClaimCode(editing!.chip_id),
    onSuccess: (res) => {
      setClaimed(res);
      setProvisioned(null);
      setWhitelisted(true);
      setSecretVersion(res.secret_version);
      qc.invalidateQueries({ queryKey: ["inventory"] });
      qc.invalidateQueries({ queryKey: ["device"] });
    },
    onError: (e: Error) => setError(e.message),
  });

  const whitelistMut = useMutation({
    mutationFn: (next: boolean) => api.setDeviceWhitelisted(editing!.chip_id, next),
    onSuccess: (res) => {
      setWhitelisted(res.whitelisted);
      qc.invalidateQueries({ queryKey: ["inventory"] });
      qc.invalidateQueries({ queryKey: ["device"] });
    },
    onError: (e: Error) => setError(e.message),
  });

  const saveMut = useMutation({
    mutationFn: (body: JaamMapInput) =>
      editing ? api.updateMap(editing.chip_id, body) : api.createMap(body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["inventory"] });
      qc.invalidateQueries({ queryKey: ["device"] });
      onClose();
      setError("");
      onSuccess?.();
    },
    onError: (e: Error) => setError(e.message),
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    saveMut.mutate(form);
  };

  return (
    <Modal open={open} onClose={onClose} title={editing ? `Редагувати ${editing.chip_id}` : "Нова JAAM-мапа"}>
      <form onSubmit={handleSubmit} className="space-y-3">
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="mb-1 block text-xs text-muted-foreground">Chip ID *</label>
            <Input value={form.chip_id} onChange={(e) => setForm({ ...form, chip_id: e.target.value })} disabled={!!editing} required className="font-mono" placeholder="напр. a1b2c3d4e5f6" />
          </div>
          <div>
            <label className="mb-1 block text-xs text-muted-foreground">Мітка</label>
            <Input value={form.map_id ?? ""} onChange={(e) => setForm({ ...form, map_id: e.target.value })} placeholder="напр. JAAM3-0029" />
          </div>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="mb-1 block text-xs text-muted-foreground">Тип</label>
            <Select value={form.hw_version ?? ""} onChange={(e) => setForm({ ...form, hw_version: e.target.value })}>
              <option value="">—</option>
              {hwVersions?.map((v) => <option key={v.id} value={v.name}>{v.name}</option>)}
              {form.hw_version && !hwVersions?.some((v) => v.name === form.hw_version) && (
                <option value={form.hw_version}>{form.hw_version}</option>
              )}
            </Select>
          </div>
          <div>
            <label className="mb-1 block text-xs text-muted-foreground">Номер замовлення</label>
            <Input value={form.order_number ?? ""} onChange={(e) => setForm({ ...form, order_number: e.target.value })} placeholder="опціонально" />
          </div>
        </div>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={form.is_prototype} onChange={(e) => setForm({ ...form, is_prototype: e.target.checked })} className="h-4 w-4 accent-primary" />
          Прототип
        </label>
        <div>
          <label className="mb-1 block text-xs text-muted-foreground">Інформація про клієнта</label>
          <Textarea rows={3} value={form.customer_info ?? ""} onChange={(e) => setForm({ ...form, customer_info: e.target.value })} placeholder="Ім'я, контакт, нотатки…" />
        </div>

        {editing && user?.role === "admin" && (
          <div className="space-y-2 rounded border border-border/[0.1] bg-muted/30 p-3">
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium text-muted-foreground">Авторизація прошивки (jaam_touch)</span>
              <Badge variant={whitelisted ? "online" : "unseen"}>{whitelisted ? "у білому списку" : "заблоковано"}</Badge>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-xs text-muted-foreground">
                {secretVersion > 0 ? `Версія секрету: ${secretVersion}` : "Секрет ще не видано"}
              </span>
              <button
                type="button"
                onClick={() => provisionMut.mutate()}
                disabled={provisionMut.isPending}
                title="Секрет одразу в hex-вигляді — для техніка з серійним кабелем (PROVISION у serial-монітор)"
                className="ml-auto rounded border border-border/[0.1] px-3 py-1.5 text-xs transition hover:bg-muted hover:text-foreground disabled:opacity-40"
              >
                {provisionMut.isPending ? <Spinner /> : secretVersion > 0 ? "Перевидати секрет" : "Видати секрет"}
              </button>
              <button
                type="button"
                onClick={() => claimCodeMut.mutate()}
                disabled={claimCodeMut.isPending}
                title="Короткий одноразовий код (24г) — кінцевий користувач вводить його на екрані пристрою (Меню > Про пристрій > Ввести код активації), без комп'ютера"
                className="rounded border border-border/[0.1] px-3 py-1.5 text-xs transition hover:bg-muted hover:text-foreground disabled:opacity-40"
              >
                {claimCodeMut.isPending ? <Spinner /> : "Видати код активації"}
              </button>
              <button
                type="button"
                onClick={() => whitelistMut.mutate(!whitelisted)}
                disabled={whitelistMut.isPending}
                className="rounded border border-border/[0.1] px-3 py-1.5 text-xs transition hover:bg-muted hover:text-foreground disabled:opacity-40"
              >
                {whitelistMut.isPending ? <Spinner /> : whitelisted ? "Заблокувати" : "Розблокувати"}
              </button>
            </div>
            {provisioned && (
              <div className="space-y-1 rounded border border-primary/30 bg-primary/5 p-2">
                <div className="text-xs text-danger">
                  Секрет показується лише один раз і ніде на сервері не зберігається — скопіюйте зараз.
                </div>
                <div className="flex items-center gap-2">
                  <code className="flex-1 select-all break-all rounded bg-muted px-2 py-1 text-xs">{provisioned.secret_hex}</code>
                  <button
                    type="button"
                    onClick={() => navigator.clipboard?.writeText(provisioned.secret_hex)}
                    className="shrink-0 rounded border border-border/[0.1] px-2 py-1 text-xs transition hover:bg-muted hover:text-foreground"
                  >
                    Копіювати
                  </button>
                </div>
              </div>
            )}
            {claimed && (
              <div className="space-y-1 rounded border border-primary/30 bg-primary/5 p-2">
                <div className="text-xs text-danger">
                  Код показується лише один раз, діє {Math.round(claimed.expires_in_s / 3600)} год і одноразовий — передайте користувачу зараз.
                </div>
                <div className="flex items-center gap-2">
                  <code className="flex-1 select-all break-all rounded bg-muted px-2 py-1 text-base tracking-wider">{claimed.claim_code}</code>
                  <button
                    type="button"
                    onClick={() => navigator.clipboard?.writeText(claimed.claim_code)}
                    className="shrink-0 rounded border border-border/[0.1] px-2 py-1 text-xs transition hover:bg-muted hover:text-foreground"
                  >
                    Копіювати
                  </button>
                </div>
              </div>
            )}
          </div>
        )}

        {error && <div className="text-sm text-danger">{error}</div>}
        <div className="flex justify-end gap-2 pt-1">
          <button type="button" onClick={onClose} className="rounded border border-border/[0.1] px-4 py-2 text-sm transition hover:bg-muted hover:text-foreground">Скасувати</button>
          <Button type="submit" disabled={saveMut.isPending}>{saveMut.isPending ? <Spinner /> : "Зберегти"}</Button>
        </div>
      </form>
    </Modal>
  );
}
