import React from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api, type JaamMap, type JaamMapInput } from "@/lib/api";
import { Button, Input, Modal, Select, Spinner, Textarea } from "@/components/ui";

const HW_VERSIONS = ["JAAM3.2", "JAAM3.1", "JAAM3.0", "JAAM2", "JAAM1", ""];

export interface JaamMapModalProps {
  open: boolean;
  onClose: () => void;
  editing?: JaamMap | null;
  onSuccess?: () => void;
}

export function JaamMapModal({ open, onClose, editing, onSuccess }: JaamMapModalProps) {
  const qc = useQueryClient();
  const empty: JaamMapInput = { chip_id: "", map_id: "", hw_version: "JAAM3.2", is_prototype: false, order_number: "", customer_info: "" };

  const [form, setForm] = React.useState<JaamMapInput>(empty);
  const [error, setError] = React.useState("");

  React.useEffect(() => {
    if (editing) {
      setForm({
        chip_id: editing.chip_id,
        map_id: editing.map_id ?? "",
        hw_version: editing.hw_version ?? "",
        is_prototype: editing.is_prototype,
        order_number: editing.order_number ?? "",
        customer_info: editing.customer_info ?? "",
      });
    } else {
      setForm(empty);
    }
    setError("");
  }, [editing, open]);

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
            <label className="mb-1 block text-xs text-muted-foreground">HW версія</label>
            <Select value={form.hw_version ?? ""} onChange={(e) => setForm({ ...form, hw_version: e.target.value })}>
              {HW_VERSIONS.map((v) => <option key={v} value={v}>{v || "—"}</option>)}
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
        {error && <div className="text-sm text-danger">{error}</div>}
        <div className="flex justify-end gap-2 pt-1">
          <button type="button" onClick={onClose} className="rounded border border-border/[0.1] px-4 py-2 text-sm transition hover:bg-muted hover:text-foreground">Скасувати</button>
          <Button type="submit" disabled={saveMut.isPending}>{saveMut.isPending ? <Spinner /> : "Зберегти"}</Button>
        </div>
      </form>
    </Modal>
  );
}
