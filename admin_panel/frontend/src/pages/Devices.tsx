import { useRef, useEffect, useState } from "react";
import { useQuery, keepPreviousData } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Search, ChevronLeft, ChevronRight } from "lucide-react";
import { api } from "@/lib/api";
import { Badge, Card, Input, Select, Spinner } from "@/components/ui";
import { cn, timeAgo } from "@/lib/utils";

export default function Devices() {
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const [type_, setType] = useState("");
  const [page, setPage] = useState(1);
  const pageSize = 50;

  const tableRef = useRef<HTMLDivElement>(null);
  const isFirstRender = useRef(true);

  const { data, isLoading, isFetching } = useQuery({
    queryKey: ["devices", q, status, type_, page],
    queryFn: () =>
      api.devices({ q, status, type: type_, page, page_size: pageSize, sort: "last_seen", order: "desc" }),
    refetchInterval: 15000,
    placeholderData: keepPreviousData,
  });

  useEffect(() => {
    if (isFirstRender.current) { isFirstRender.current = false; return; }
    tableRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [page]);

  const totalPages = data ? Math.max(1, Math.ceil(data.total / pageSize)) : 1;
  const goPage = (dir: number, e: React.MouseEvent<HTMLButtonElement>) => { setPage((p) => p + dir); e.currentTarget.blur(); };

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
            onChange={(e) => { setQ(e.target.value); setPage(1); }} />
        </div>
        <Select value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }}>
          <option value="">Усі статуси</option>
          <option value="online">Онлайн</option>
          <option value="offline">Офлайн</option>
        </Select>
        <Select value={type_} onChange={(e) => { setType(e.target.value); setPage(1); }}>
          <option value="">Усі типи</option>
          <option value="jaam">Офіційні JAAM</option>
          <option value="self">Самозбірки</option>
        </Select>
      </div>

      <div ref={tableRef}>
        <div className={cn("transition-opacity duration-200", isFetching && "opacity-60 pointer-events-none")}>
          <Card className="overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border/[0.1] text-left text-xs uppercase tracking-wide text-muted-foreground">
                    <th className="px-3 py-3 font-medium sm:px-4">Статус</th>
                    <th className="px-3 py-3 font-medium sm:px-4">Chip ID</th>
                    <th className="hidden px-4 py-3 font-medium sm:table-cell">Тип</th>
                    <th className="hidden px-4 py-3 font-medium md:table-cell">Прошивка</th>
                    <th className="hidden px-4 py-3 font-medium lg:table-cell">HW</th>
                    <th className="px-3 py-3 font-medium sm:px-4">Локація</th>
                    <th className="hidden px-4 py-3 font-medium lg:table-cell">Сервер</th>
                    <th className="px-3 py-3 font-medium sm:px-4">Остання акт.</th>
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
                            {d.is_online ? "онлайн" : "офлайн"}
                          </Badge>
                        </td>
                        <td className="px-3 py-3 sm:px-4">
                          <Link to={`/devices/${d.chip_id}`} className="font-mono text-xs text-primary hover:underline sm:text-sm">
                            {d.chip_id}
                          </Link>
                          {d.firmware_id && <span className="ml-1 hidden text-xs text-muted-foreground sm:inline">{d.firmware_id}</span>}
                        </td>
                        <td className="hidden px-4 py-3 sm:table-cell">
                          {d.is_jaam ? (
                            <span className="inline-flex items-center gap-1 rounded-full border border-primary/30 bg-primary/10 px-2 py-0.5 text-xs font-medium text-primary" title={d.customer_info ?? undefined}>
                              {d.hw_version ?? "JAAM"}
                              {d.is_prototype ? " · прот." : ""}
                            </span>
                          ) : (
                            <span className="inline-flex items-center rounded-full border border-border/[0.15] bg-muted px-2 py-0.5 text-xs font-medium text-muted-foreground">
                              SELF
                            </span>
                          )}
                        </td>
                        <td className="hidden px-4 py-3 font-mono text-xs md:table-cell">{d.firmware ?? "—"}</td>
                        <td className="hidden px-4 py-3 lg:table-cell">{d.hw_type ?? "—"}</td>
                        <td className="max-w-[120px] truncate px-3 py-3 text-xs text-muted-foreground sm:max-w-none sm:px-4 sm:text-sm">
                          {[d.city, d.region].filter(Boolean).join(", ") || "—"}
                        </td>
                        <td className="hidden px-4 py-3 text-xs text-muted-foreground lg:table-cell">{d.last_server ?? "—"}</td>
                        <td className="px-3 py-3 text-xs text-muted-foreground sm:px-4 sm:text-sm" title={d.last_seen}>
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
          <button disabled={page <= 1} onClick={(e) => goPage(-1, e)}
            className="flex items-center gap-1 rounded border border-border/[0.1] px-3 py-1.5 transition hover:bg-muted hover:text-foreground disabled:opacity-40">
            <ChevronLeft className="h-4 w-4" /> Назад
          </button>
          <button disabled={page >= totalPages} onClick={(e) => goPage(1, e)}
            className="flex items-center gap-1 rounded border border-border/[0.1] px-3 py-1.5 transition hover:bg-muted hover:text-foreground disabled:opacity-40">
            Далі <ChevronRight className="h-4 w-4" />
          </button>
        </div>
      </div>
    </div>
  );
}
