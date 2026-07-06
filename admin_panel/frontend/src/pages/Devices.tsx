import { useQuery, keepPreviousData } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";
import { Search, ChevronLeft, ChevronRight, FlaskConical } from "lucide-react";
import { api } from "@/lib/api";
import { Badge, Card, Input, Select, Spinner, SortTh } from "@/components/ui";
import { cn, timeAgo } from "@/lib/utils";

export default function Devices() {
  const [searchParams, setSearchParams] = useSearchParams();

  const q      = searchParams.get("q") ?? "";
  const status = searchParams.get("status") ?? "";
  const type_  = searchParams.get("type") ?? "";
  const sort   = searchParams.get("sort") ?? "last_seen";
  const dir    = (searchParams.get("dir") ?? "desc") as "asc" | "desc";
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

  const { data, isLoading, isFetching } = useQuery({
    queryKey: ["devices", q, status, type_, sort, dir, page],
    queryFn: () => api.devices({ q, status, type: type_, page, page_size: pageSize, sort, order: dir }),
    refetchInterval: 15000,
    placeholderData: keepPreviousData,
  });

  const totalPages = data ? Math.max(1, Math.ceil(data.total / pageSize)) : 1;

  return (
    <div className="space-y-4 p-4 sm:p-6">
      <div className="flex items-end justify-between">
        <div>
          <h1 className="text-xl font-bold sm:text-2xl">Мапи</h1>
          <p className="text-sm text-muted-foreground">
            {data ? `${data.total} у реєстрі` : "Завантаження…"}
          </p>
        </div>
        {isFetching && <Spinner className="h-4 w-4" />}
      </div>

      <div className="flex flex-wrap gap-2">
        <div className="relative min-w-0 flex-1">
          <Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input className="pl-9" placeholder="Пошук за chip_id або містом…" value={q}
            onChange={(e) => set({ q: e.target.value })} />
        </div>
        <Select value={status} onChange={(e) => set({ status: e.target.value })}>
          <option value="">Усі статуси</option>
          <option value="online">Онлайн</option>
          <option value="offline">Офлайн</option>
        </Select>
        <Select value={type_} onChange={(e) => set({ type: e.target.value })}>
          <option value="">Усі типи</option>
          <option value="jaam">Офіційні JAAM</option>
          <option value="self">Самозбірки</option>
        </Select>
      </div>

      <div>
        <div className={cn("transition-opacity duration-200", isFetching && "opacity-60 pointer-events-none")}>
          <Card className="overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border/[0.1] text-left">
                    <SortTh col="is_online" label="Статус" sort={sort} dir={dir} onSort={onSort} />
                    <SortTh col="chip_id" label="Chip ID" sort={sort} dir={dir} onSort={onSort} />
                    <SortTh col="hw_version" label="Тип" sort={sort} dir={dir} onSort={onSort} className="hidden sm:table-cell" />
                    <SortTh col="firmware" label="Прошивка" sort={sort} dir={dir} onSort={onSort} className="hidden md:table-cell" />
                    <SortTh col="hw_type" label="HW" sort={sort} dir={dir} onSort={onSort} className="hidden lg:table-cell" />
                    <SortTh col="region" label="Локація" sort={sort} dir={dir} onSort={onSort} />
                    <SortTh col="last_server" label="Сервер" sort={sort} dir={dir} onSort={onSort} className="hidden lg:table-cell" />
                    <SortTh col="last_seen" label="Остання акт." sort={sort} dir={dir} onSort={onSort} />
                  </tr>
                </thead>
                <tbody>
                  {isLoading ? (
                    <tr><td colSpan={8} className="py-16 text-center"><Spinner className="mx-auto h-6 w-6" /></td></tr>
                  ) : data && data.items.length > 0 ? (
                    data.items.map((d) => (
                      <tr key={d.chip_id} className="border-b border-border/[0.07] transition hover:bg-muted/40">
                        <td className="px-3 py-3 sm:px-4">
                          <Badge variant={d.is_online ? "online" : "offline"}>
                            {d.is_online ? "online" : "offline"}
                          </Badge>
                        </td>
                        <td className="px-3 py-3 sm:px-4">
                          <Link to={`/devices/${d.chip_id}`} className="font-mono text-xs text-primary hover:underline sm:text-sm">
                            {d.chip_id}
                          </Link>
                          {d.map_id && <div className="font-mono text-[11px] text-muted-foreground">{d.map_id}</div>}
                        </td>
                        <td className="hidden px-4 py-3 sm:table-cell">
                          {d.is_jaam ? (
                            <span className="inline-flex items-center gap-1 rounded-full border border-primary/30 bg-primary/10 px-2 py-0.5 text-xs font-medium text-primary" title={d.customer_info ?? undefined}>
                              {d.is_prototype && <FlaskConical className="h-3 w-3 shrink-0" />}
                              {d.hw_version ?? "JAAM"}
                            </span>
                          ) : (
                            <span className="inline-flex items-center rounded-full border border-border/[0.15] bg-muted px-2 py-0.5 text-xs font-medium text-muted-foreground">
                              SELF
                            </span>
                          )}
                        </td>
                        <td className="hidden px-4 py-3 font-mono text-xs md:table-cell">{d.firmware ?? "—"}</td>
                        <td className="hidden px-4 py-3 lg:table-cell">{d.hw_type ?? "—"}</td>
                        <td className="max-w-[140px] truncate px-3 py-3 text-muted-foreground sm:max-w-[240px] sm:px-4">
                          {[d.city, d.region].filter(Boolean).join(", ") || "—"}
                        </td>
                        <td className="hidden px-4 py-3 text-muted-foreground lg:table-cell">{d.last_server ?? "—"}</td>
                        <td className="px-3 py-3 text-muted-foreground sm:px-4" title={d.last_seen}>
                          {timeAgo(d.last_seen)}
                        </td>
                      </tr>
                    ))
                  ) : (
                    <tr><td colSpan={8} className="py-16 text-center text-muted-foreground">Нічого не знайдено</td></tr>
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
            className="flex items-center gap-1 rounded border border-border/[0.1] px-3 py-1.5 transition hover:bg-muted hover:text-foreground disabled:opacity-40">
            <ChevronLeft className="h-4 w-4" /> Назад
          </button>
          <button disabled={page >= totalPages} onClick={() => goPage(1)}
            className="flex items-center gap-1 rounded border border-border/[0.1] px-3 py-1.5 transition hover:bg-muted hover:text-foreground disabled:opacity-40">
            Далі <ChevronRight className="h-4 w-4" />
          </button>
        </div>
      </div>
    </div>
  );
}
