import { useRef, useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient, keepPreviousData } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Plus, Search, Pencil, Trash2, FlaskConical } from "lucide-react";
import { api, type JaamMap, type JaamMapInput } from "@/lib/api";
import { Badge, Button, Card, Input, Modal, Select, Spinner, SortTh, Textarea } from "@/components/ui";
import { cn, timeAgo } from "@/lib/utils";

const HW_VERSIONS = ["JAAM3.2", "JAAM3.1", "JAAM3.0", "JAAM2", "JAAM1", ""];
const EMPTY: JaamMapInput = { chip_id: "", map_id: "", hw_version: "JAAM3.2", is_prototype: false, order_number: "", customer_info: "" };

export default function Inventory() {
  const qc = useQueryClient();
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const [sort, setSort] = useState("chip_id");
  const [dir, setDir] = useState<"asc" | "desc">("asc");
  const [page, setPage] = useState(1);
  const pageSize = 50;

  const onSort = (col: string) => {
    if (col === sort) setDir((d) => (d === "asc" ? "desc" : "asc"));
    else { setSort(col); setDir("asc"); }
    setPage(1);
  };

  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<JaamMap | null>(null);
  const [form, setForm] = useState<JaamMapInput>(EMPTY);
  const [error, setError] = useState("");

  const tableRef = useRef<HTMLDivElement>(null);
  const isFirstRender = useRef(true);

  const { data, isLoading, isFetching } = useQuery({
    queryKey: ["inventory", q, status, sort, dir, page],
    queryFn: () => api.inventory({ q, status, sort, order: dir, page, page_size: pageSize }),
    refetchInterval: 20000,
    placeholderData: keepPreviousData,
  });

  useEffect(() => {
    if (isFirstRender.current) { isFirstRender.current = false; return; }
    tableRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [page]);

  const invalidate = () => qc.invalidateQueries({ queryKey: ["inventory"] });

  const saveMut = useMutation({
    mutationFn: (body: JaamMapInput) =>
      editing ? api.updateMap(editing.chip_id, body) : api.createMap(body),
    onSuccess: () => { invalidate(); setModalOpen(false); setError(""); },
    onError: (e: Error) => setError(e.message),
  });

  const delMut = useMutation({
    mutationFn: (chipId: string) => api.deleteMap(chipId),
    onSuccess: invalidate,
  });

  const openAdd = () => { setEditing(null); setForm(EMPTY); setError(""); setModalOpen(true); };
  const openEdit = (m: JaamMap) => {
    setEditing(m);
    setForm({ chip_id: m.chip_id, map_id: m.map_id ?? "", hw_version: m.hw_version ?? "", is_prototype: m.is_prototype, order_number: m.order_number ?? "", customer_info: m.customer_info ?? "" });
    setError("");
    setModalOpen(true);
  };

  const totalPages = data ? Math.max(1, Math.ceil(data.total / pageSize)) : 1;
  const goPage = (dir: number, e: React.MouseEvent<HTMLButtonElement>) => { setPage((p) => p + dir); e.currentTarget.blur(); };

  return (
    <div className="space-y-4 p-4 sm:p-6">
      <div className="flex items-end justify-between">
        <div>
          <h1 className="text-xl font-bold sm:text-2xl">Реєстр JAAM</h1>
          <p className="text-sm text-muted-foreground">
            {data ? `${data.total} офіційних мап` : "Завантаження…"}
          </p>
        </div>
        <Button onClick={openAdd} className="shrink-0">
          <Plus className="h-4 w-4" /> <span className="hidden sm:inline">Додати мапу</span>
        </Button>
      </div>

      <div className="flex flex-wrap gap-2">
        <div className="relative min-w-0 flex-1">
          <Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input
            className="pl-9"
            placeholder="Пошук за chip_id, замовленням…"
            value={q}
            onChange={(e) => { setQ(e.target.value); setPage(1); }}
          />
        </div>
        <Select value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }}>
          <option value="">Будь-який стан</option>
          <option value="online">Онлайн</option>
          <option value="offline">Офлайн</option>
          <option value="never">Ніколи не бачили</option>
        </Select>
        {isFetching && <Spinner className="h-5 w-5 self-center" />}
      </div>

      <div ref={tableRef}>
        <div className={cn("transition-opacity duration-200", isFetching && "opacity-60 pointer-events-none")}>
          <Card className="overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border/[0.1] text-left">
                    <SortTh col="is_online" label="Стан" sort={sort} dir={dir} onSort={onSort} />
                    <SortTh col="chip_id" label="Chip ID" sort={sort} dir={dir} onSort={onSort} />
                    <SortTh col="hw_version" label="HW версія" sort={sort} dir={dir} onSort={onSort} className="hidden sm:table-cell" />
                    <SortTh col="order_number" label="Замовлення" sort={sort} dir={dir} onSort={onSort} className="hidden md:table-cell" />
                    <SortTh col="customer_info" label="Клієнт" sort={sort} dir={dir} onSort={onSort} />
                    <SortTh col="firmware" label="Прошивка" sort={sort} dir={dir} onSort={onSort} className="hidden lg:table-cell" />
                    <th className="px-3 py-3 sm:px-4"></th>
                  </tr>
                </thead>
                <tbody>
                  {isLoading ? (
                    <tr><td colSpan={7} className="py-16 text-center"><Spinner className="mx-auto h-6 w-6" /></td></tr>
                  ) : data && data.items.length > 0 ? (
                    data.items.map((m) => (
                      <tr key={m.chip_id} className="border-b border-border/[0.07] transition hover:bg-muted/40">
                        <td className="px-3 py-3 sm:px-4">
                          {!m.ever_seen ? (
                            <Badge variant="muted">unseen</Badge>
                          ) : m.is_online ? (
                            <Badge variant="online">online</Badge>
                          ) : (
                            <Badge variant="offline">offline</Badge>
                          )}
                        </td>
                        <td className="px-3 py-3 sm:px-4">
                          <Link to={`/devices/${m.chip_id}`} className="font-mono text-xs text-primary hover:underline sm:text-sm">
                            {m.chip_id}
                          </Link>
                        </td>
                        <td className="hidden px-4 py-3 sm:table-cell">
                          <span className="inline-flex items-center gap-1.5">
                            {m.hw_version ?? "—"}
                            {m.is_prototype && <FlaskConical className="h-3.5 w-3.5 text-warning" />}
                          </span>
                        </td>
                        <td className="hidden px-4 py-3 font-mono text-xs md:table-cell">{m.order_number ?? "—"}</td>
                        <td className="max-w-[140px] truncate px-3 py-3 text-muted-foreground sm:max-w-[240px] sm:px-4" title={m.customer_info ?? ""}>
                          {m.customer_info ?? "—"}
                        </td>
                        <td className="hidden px-4 py-3 font-mono text-xs text-muted-foreground lg:table-cell">
                          {m.firmware ?? "—"}
                          {m.ever_seen && m.last_seen && <div className="text-[10px]">{timeAgo(m.last_seen)}</div>}
                        </td>
                        <td className="px-3 py-3 sm:px-4">
                          <div className="flex justify-end gap-1">
                            <button onClick={() => openEdit(m)} className="rounded-md p-1.5 text-muted-foreground transition hover:bg-muted hover:text-foreground" title="Редагувати">
                              <Pencil className="h-4 w-4" />
                            </button>
                            <button
                              onClick={() => { if (confirm(`Видалити ${m.chip_id} з реєстру?`)) delMut.mutate(m.chip_id); }}
                              disabled={delMut.isPending}
                              className="rounded-md p-1.5 text-muted-foreground transition hover:bg-danger/15 hover:text-danger disabled:opacity-40"
                              title="Видалити"
                            >
                              <Trash2 className="h-4 w-4" />
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))
                  ) : (
                    <tr><td colSpan={7} className="py-16 text-center text-muted-foreground">Реєстр порожній</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </Card>
        </div>
      </div>

      <div className="flex items-center justify-between text-sm text-muted-foreground">
        <span>Стор. {page} з {totalPages}</span>
        <div className="flex gap-2">
          <button disabled={page <= 1} onClick={(e) => goPage(-1, e)}
            className="rounded border border-border/[0.1] px-3 py-1.5 transition hover:bg-muted hover:text-foreground disabled:opacity-40">
            ← Назад
          </button>
          <button disabled={page >= totalPages} onClick={(e) => goPage(1, e)}
            className="rounded border border-border/[0.1] px-3 py-1.5 transition hover:bg-muted hover:text-foreground disabled:opacity-40">
            Далі →
          </button>
        </div>
      </div>

      <Modal open={modalOpen} onClose={() => setModalOpen(false)} title={editing ? `Редагувати ${editing.chip_id}` : "Нова JAAM-мапа"}>
        <form onSubmit={(e) => { e.preventDefault(); saveMut.mutate(form); }} className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="mb-1 block text-xs text-muted-foreground">Chip ID *</label>
              <Input value={form.chip_id} onChange={(e) => setForm({ ...form, chip_id: e.target.value })} disabled={!!editing} required className="font-mono" placeholder="напр. a1b2c3d4e5f6" />
            </div>
            <div>
              <label className="mb-1 block text-xs text-muted-foreground">ID (мітка)</label>
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
            <button type="button" onClick={() => setModalOpen(false)} className="rounded border border-border/[0.1] px-4 py-2 text-sm transition hover:bg-muted hover:text-foreground">Скасувати</button>
            <Button type="submit" disabled={saveMut.isPending}>{saveMut.isPending ? <Spinner /> : "Зберегти"}</Button>
          </div>
        </form>
      </Modal>
    </div>
  );
}
