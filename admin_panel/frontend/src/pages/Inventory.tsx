import { useState } from "react";
import { useQuery, useQueryClient, keepPreviousData, useMutation } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";
import { Plus, Search, Pencil, Trash2, FlaskConical } from "lucide-react";
import { api, type JaamMap } from "@/lib/api";
import { Badge, Button, Card, Input, Select, Spinner, SortTh } from "@/components/ui";
import { JaamMapModal } from "@/components/JaamMapModal";
import { cn } from "@/lib/utils";

export default function Inventory() {
  const qc = useQueryClient();
  const [searchParams, setSearchParams] = useSearchParams();

  const q      = searchParams.get("q") ?? "";
  const status = searchParams.get("status") ?? "";
  const sort   = searchParams.get("sort") ?? "chip_id";
  const dir    = (searchParams.get("dir") ?? "asc") as "asc" | "desc";
  const page   = Math.max(1, parseInt(searchParams.get("page") ?? "1", 10) || 1);
  const pageSize = 50;

  const set = (updates: Record<string, string>, resetPage = true) => {
    setSearchParams(prev => {
      const next = new URLSearchParams(prev);
      for (const [k, v] of Object.entries(updates)) {
        if (v) next.set(k, v); else next.delete(k);
      }
      if (resetPage) next.delete("page");
      return next;
    }, { replace: true });
  };

  const onSort = (col: string) => {
    if (col === sort) set({ sort: col, dir: dir === "asc" ? "desc" : "asc" });
    else set({ sort: col, dir: "asc" });
  };

  const goPage = (delta: number) => {
    const p = page + delta;
    setSearchParams(prev => {
      const next = new URLSearchParams(prev);
      if (p <= 1) next.delete("page"); else next.set("page", String(p));
      return next;
    }, { replace: true });
  };

  const [editing, setEditing] = useState<JaamMap | null>(null);
  const [modalOpen, setModalOpen] = useState(false);

  const { data, isLoading, isFetching } = useQuery({
    queryKey: ["inventory", q, status, sort, dir, page],
    queryFn: () => api.inventory({ q, status, sort, order: dir, page, page_size: pageSize }),
    refetchInterval: 20000,
    placeholderData: keepPreviousData,
  });

  const invalidate = () => qc.invalidateQueries({ queryKey: ["inventory"] });

  const delMut = useMutation({
    mutationFn: (chipId: string) => api.deleteMap(chipId),
    onSuccess: invalidate,
  });

  const openAdd = () => {
    setEditing(null);
    setModalOpen(true);
  };
  const openEdit = (m: JaamMap) => {
    setEditing(m);
    setModalOpen(true);
  };

  const totalPages = data ? Math.max(1, Math.ceil(data.total / pageSize)) : 1;

  return (
    <div className="space-y-4 p-4 sm:p-6">
      <div className="flex items-end justify-between">
        <div>
          <h1 className="text-xl font-bold sm:text-2xl">Реєстр JAAM</h1>
          <p className="text-sm text-muted-foreground">
            {data ? `${data.total} офіційних мап` : "Завантаження…"}
          </p>
        </div>
        <Button onClick={() => openAdd()} className="shrink-0">
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
            onChange={(e) => set({ q: e.target.value })}
          />
        </div>
        <Select value={status} onChange={(e) => set({ status: e.target.value })}>
          <option value="">Будь-який стан</option>
          <option value="online">Онлайн</option>
          <option value="offline">Офлайн</option>
          <option value="never">Ніколи не бачили</option>
        </Select>
        {isFetching && <Spinner className="h-5 w-5 self-center" />}
      </div>

      <div>
        <div className={cn("transition-opacity duration-200", isFetching && "opacity-60 pointer-events-none")}>
          <Card className="overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-sm [&_tbody_td]:align-middle">
                <thead>
                  <tr className="border-b border-border/[0.1] text-left">
                    <SortTh col="is_online" label="Статус" sort={sort} dir={dir} onSort={onSort} />
                    <SortTh col="chip_id" label="Chip ID" sort={sort} dir={dir} onSort={onSort} />
                    <SortTh col="hw_version" label="Тип" sort={sort} dir={dir} onSort={onSort} className="hidden sm:table-cell" />
                    <SortTh col="map_id" label="Мітка" sort={sort} dir={dir} onSort={onSort} className="hidden md:table-cell" />
                    <SortTh col="order_number" label="Замовлення" sort={sort} dir={dir} onSort={onSort} />
                    <SortTh col="customer_info" label="Клієнт" sort={sort} dir={dir} onSort={onSort} />
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
                            <Badge variant="unseen">unseen</Badge>
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
                          {m.firmware_id && <div className="font-mono text-[11px] text-muted-foreground">{m.firmware_id}</div>}
                        </td>
                        <td className="hidden px-4 py-3 sm:table-cell">
                          <span className="inline-flex items-center gap-1 rounded-full border border-primary/30 bg-primary/10 px-2 py-0.5 text-xs font-medium text-primary" title={m.customer_info ?? undefined}>
                            {m.is_prototype && <FlaskConical className="h-3 w-3 shrink-0" />}
                            {m.hw_version ?? "JAAM"}
                          </span>
                        </td>
                        <td className="hidden px-4 py-3 font-mono text-xs md:table-cell">{m.map_id ?? "—"}</td>
                        <td className="px-3 py-3 font-mono text-xs sm:px-4">{m.order_number ?? "—"}</td>
                        <td className="max-w-[140px] truncate px-3 py-3 text-muted-foreground sm:max-w-[240px] sm:px-4" title={m.customer_info ?? ""}>
                          {m.customer_info ?? "—"}
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
          <button disabled={page <= 1} onClick={() => goPage(-1)}
            className="rounded border border-border/[0.1] px-3 py-1.5 transition hover:bg-muted hover:text-foreground disabled:opacity-40">
            ← Назад
          </button>
          <button disabled={page >= totalPages} onClick={() => goPage(1)}
            className="rounded border border-border/[0.1] px-3 py-1.5 transition hover:bg-muted hover:text-foreground disabled:opacity-40">
            Далі →
          </button>
        </div>
      </div>

      <JaamMapModal
        open={modalOpen}
        onClose={() => {
          setModalOpen(false);
          setEditing(null);
        }}
        editing={editing}
      />
    </div>
  );
}
