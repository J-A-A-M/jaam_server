import { Fragment } from "react";
import { useQuery, keepPreviousData } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";
import { Search } from "lucide-react";
import { api } from "@/lib/api";
import { Card, Input, RelativeTime, Select, Spinner, SortTh } from "@/components/ui";
import { cn } from "@/lib/utils";

const EVENT_LABEL: Record<string, string> = {
  online:             "з'явилась онлайн",
  offline:            "пішла в офлайн",
  firmware_change:    "оновлення прошивки",
  firmware_id_change: "зміна ID мапи",
  geo_change:         "зміна локації",
  ip_change:          "зміна IP",
  first_seen:         "нова мапа",
};

const EVENT_TYPES = [
  { value: "",                   label: "Будь-який тип" },
  { value: "online",             label: "з'явилась онлайн" },
  { value: "offline",            label: "пішла в офлайн" },
  { value: "first_seen",         label: "нова мапа" },
  { value: "firmware_change",    label: "оновлення прошивки" },
  { value: "firmware_id_change", label: "зміна ID мапи" },
  { value: "geo_change",         label: "зміна локації" },
  { value: "ip_change",          label: "зміна IP" },
];

const PERIODS = [
  { value: "",      label: "Будь-який час" },
  { value: "today", label: "Сьогодні" },
  { value: "week",  label: "7 днів" },
  { value: "month", label: "30 днів" },
];

const DOT: Record<string, string> = {
  online:     "bg-success",
  offline:    "bg-muted-foreground/50",
  first_seen: "bg-primary",
};

function eventDetail(type: string, details: string | null): string | null {
  if (!details) return null;
  try {
    const d = JSON.parse(details) as Record<string, string | null>;
    switch (type) {
      case "first_seen":         return d.firmware ?? null;
      case "online":             return d.server ?? null;
      case "firmware_change":    return d.from && d.to ? `${d.from} → ${d.to}` : null;
      case "firmware_id_change": return `${d.from ?? "—"} → ${d.to ?? "—"}`;
      case "geo_change":         return d.from && d.to ? `${d.from} → ${d.to}` : null;
      case "ip_change":          return d.from && d.to ? `${d.from} → ${d.to}` : null;
      default:                   return null;
    }
  } catch { return null; }
}

const PAGE_SIZE = 50;

export default function Events() {
  const [searchParams, setSearchParams] = useSearchParams();

  const q      = searchParams.get("q")      ?? "";
  const type   = searchParams.get("type")   ?? "";
  const period = searchParams.get("period") ?? "";
  const sort   = searchParams.get("sort")   ?? "ts";
  const dir    = (searchParams.get("dir")   ?? "desc") as "asc" | "desc";
  const page   = Math.max(1, parseInt(searchParams.get("page") ?? "1", 10) || 1);

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
    else set({ sort: col, dir: col === "ts" ? "desc" : "asc" });
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
    queryKey: ["events", q, type, period, sort, dir, page],
    queryFn: () => api.events({ q, type, period, sort, order: dir, page, pageSize: PAGE_SIZE }),
    refetchInterval: 15000,
    placeholderData: keepPreviousData,
  });

  const totalPages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1;

  return (
    <div className="space-y-4 p-4 sm:p-6">
      <div className="flex items-end justify-between">
        <div>
          <h1 className="text-xl font-bold sm:text-2xl">Події</h1>
          <p className="text-sm text-muted-foreground">
            {data ? `${data.total} подій` : "Завантаження…"}
          </p>
        </div>
      </div>

      <div className="flex flex-wrap gap-2">
        <div className="relative min-w-0 flex-1">
          <Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input
            className="pl-9"
            placeholder="Пошук за chip_id або деталями…"
            value={q}
            onChange={(e) => set({ q: e.target.value })}
          />
        </div>
        <Select value={type} onChange={(e) => set({ type: e.target.value })}>
          {EVENT_TYPES.map(({ value, label }) => (
            <option key={value} value={value}>{label}</option>
          ))}
        </Select>
        <Select value={period} onChange={(e) => set({ period: e.target.value })}>
          {PERIODS.map(({ value, label }) => (
            <option key={value} value={value}>{label}</option>
          ))}
        </Select>
        {isFetching && <Spinner className="h-5 w-5 self-center" />}
      </div>

      <div className={cn("transition-opacity duration-200", isFetching && "opacity-60 pointer-events-none")}>
        <Card className="overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm [&_tbody_td]:align-middle">
              <thead>
                <tr className="border-b border-border/[0.1] text-left">
                  <SortTh col="type"    label="Тип"     sort={sort} dir={dir} onSort={onSort} />
                  <SortTh col="chip_id" label="Chip ID" sort={sort} dir={dir} onSort={onSort} />
                  <th className="hidden px-4 py-3 text-xs font-medium text-muted-foreground md:table-cell">Деталі</th>
                  <SortTh col="ts" label="Час" sort={sort} dir={dir} onSort={onSort} className="text-right" />
                </tr>
              </thead>
              <tbody>
                {isLoading ? (
                  <tr><td colSpan={4} className="py-16 text-center"><Spinner className="mx-auto h-6 w-6" /></td></tr>
                ) : data && data.items.length > 0 ? (
                  data.items.map((e) => {
                    const detail = eventDetail(e.type, e.details);
                    const dot = DOT[e.type] ?? "bg-primary/40";
                    return (
                      <Fragment key={e.id}>
                        <tr className={cn(
                          "transition hover:bg-muted/40",
                          detail ? "md:border-b md:border-border/[0.07]" : "border-b border-border/[0.07]",
                        )}>
                          <td className="px-3 py-3 sm:px-4">
                            <div className="flex items-center gap-2">
                              <span className={cn("h-1.5 w-1.5 shrink-0 rounded-full", dot)} />
                              <span className="text-xs">{EVENT_LABEL[e.type] ?? e.type}</span>
                            </div>
                          </td>
                          <td className="px-3 py-3 sm:px-4">
                            {e.chip_id ? (
                              <Link
                                to={`/devices/${encodeURIComponent(e.chip_id)}`}
                                className="font-mono text-xs text-primary hover:underline"
                              >
                                {e.chip_id}
                              </Link>
                            ) : (
                              <span className="text-muted-foreground">—</span>
                            )}
                          </td>
                          <td className="hidden px-4 py-3 font-mono text-xs text-muted-foreground md:table-cell">
                            {detail ?? "—"}
                          </td>
                          <td className="px-3 py-3 sm:px-4 text-right">
                            <RelativeTime ts={e.ts} className="text-xs text-muted-foreground" />
                          </td>
                        </tr>
                        {detail && (
                          <tr className="border-b border-border/[0.07] transition hover:bg-muted/40 md:hidden">
                            <td colSpan={4} className="px-3 pb-2.5 pt-0 font-mono text-[11px] text-muted-foreground">
                              {detail}
                            </td>
                          </tr>
                        )}
                      </Fragment>
                    );
                  })
                ) : (
                  <tr><td colSpan={4} className="py-16 text-center text-muted-foreground">Подій не знайдено</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </Card>
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
    </div>
  );
}
