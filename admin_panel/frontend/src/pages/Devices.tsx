import { useState } from "react";
import { useQuery, keepPreviousData } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Search, ChevronLeft, ChevronRight } from "lucide-react";
import { api } from "@/lib/api";
import { Badge, Card, Input, Select, Spinner } from "@/components/ui";
import { timeAgo } from "@/lib/utils";

export default function Devices() {
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const [type_, setType] = useState("");
  const [page, setPage] = useState(1);
  const pageSize = 50;

  const { data, isLoading, isFetching } = useQuery({
    queryKey: ["devices", q, status, type_, page],
    queryFn: () =>
      api.devices({ q, status, type: type_, page, page_size: pageSize, sort: "last_seen", order: "desc" }),
    refetchInterval: 15000,
    placeholderData: keepPreviousData,
  });

  const totalPages = data ? Math.max(1, Math.ceil(data.total / pageSize)) : 1;

  return (
    <div className="space-y-4 p-6">
      <div className="flex items-end justify-between">
        <div>
          <h1 className="text-2xl font-bold">Мапи</h1>
          <p className="text-sm text-muted-foreground">
            {data ? `${data.total} у реєстрі` : "Завантаження…"}
          </p>
        </div>
        {isFetching && <Spinner className="h-4 w-4" />}
      </div>

      <div className="flex flex-wrap gap-2">
        <div className="relative flex-1 min-w-[240px]">
          <Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input
            className="pl-9"
            placeholder="Пошук за chip_id, ID або містом…"
            value={q}
            onChange={(e) => {
              setQ(e.target.value);
              setPage(1);
            }}
          />
        </div>
        <Select
          value={status}
          onChange={(e) => {
            setStatus(e.target.value);
            setPage(1);
          }}
        >
          <option value="">Усі статуси</option>
          <option value="online">Онлайн</option>
          <option value="offline">Офлайн</option>
        </Select>
        <Select
          value={type_}
          onChange={(e) => {
            setType(e.target.value);
            setPage(1);
          }}
        >
          <option value="">Усі типи</option>
          <option value="jaam">Офіційні JAAM</option>
          <option value="self">Самозбірки</option>
        </Select>
      </div>

      <Card className="overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-left text-xs uppercase tracking-wide text-muted-foreground">
                <th className="px-4 py-3 font-medium">Статус</th>
                <th className="px-4 py-3 font-medium">Chip ID</th>
                <th className="px-4 py-3 font-medium">Тип</th>
                <th className="px-4 py-3 font-medium">Прошивка</th>
                <th className="px-4 py-3 font-medium">HW</th>
                <th className="px-4 py-3 font-medium">Локація</th>
                <th className="px-4 py-3 font-medium">Сервер</th>
                <th className="px-4 py-3 font-medium">Остання активність</th>
              </tr>
            </thead>
            <tbody>
              {isLoading ? (
                <tr>
                  <td colSpan={8} className="py-16 text-center">
                    <Spinner className="mx-auto h-6 w-6" />
                  </td>
                </tr>
              ) : data && data.items.length > 0 ? (
                data.items.map((d) => (
                  <tr key={d.chip_id} className="border-b border-border/50 transition hover:bg-muted/40">
                    <td className="px-4 py-3">
                      <Badge variant={d.is_online ? "online" : "offline"}>
                        {d.is_online ? "онлайн" : "офлайн"}
                      </Badge>
                    </td>
                    <td className="px-4 py-3">
                      <Link to={`/devices/${d.chip_id}`} className="font-mono text-primary hover:underline">
                        {d.chip_id}
                      </Link>
                      {d.custom_id && <span className="ml-2 text-xs text-muted-foreground">{d.custom_id}</span>}
                    </td>
                    <td className="px-4 py-3">
                      {d.is_jaam ? (
                        <span
                          className="inline-flex items-center gap-1 rounded-full border border-primary/30 bg-primary/10 px-2 py-0.5 text-xs font-medium text-primary"
                          title={d.customer_info ?? undefined}
                        >
                          JAAM{d.hw_version ? ` ${d.hw_version}` : ""}
                          {d.is_prototype ? " · прототип" : ""}
                        </span>
                      ) : (
                        <span className="text-xs text-muted-foreground">самозбірка</span>
                      )}
                    </td>
                    <td className="px-4 py-3 font-mono text-xs">{d.firmware ?? "—"}</td>
                    <td className="px-4 py-3">{d.hw_type ?? "—"}</td>
                    <td className="px-4 py-3 text-muted-foreground">
                      {[d.city, d.region, d.country].filter(Boolean).join(", ") || "—"}
                    </td>
                    <td className="px-4 py-3 text-xs text-muted-foreground">{d.last_server ?? "—"}</td>
                    <td className="px-4 py-3 text-muted-foreground" title={d.last_seen}>
                      {timeAgo(d.last_seen)}
                    </td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={8} className="py-16 text-center text-muted-foreground">
                    Нічого не знайдено
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </Card>

      <div className="flex items-center justify-between text-sm text-muted-foreground">
        <span>
          Сторінка {page} з {totalPages}
        </span>
        <div className="flex gap-2">
          <button
            disabled={page <= 1}
            onClick={() => setPage((p) => p - 1)}
            className="flex items-center gap-1 rounded-lg border border-border px-3 py-1.5 transition hover:bg-muted disabled:opacity-40"
          >
            <ChevronLeft className="h-4 w-4" /> Назад
          </button>
          <button
            disabled={page >= totalPages}
            onClick={() => setPage((p) => p + 1)}
            className="flex items-center gap-1 rounded-lg border border-border px-3 py-1.5 transition hover:bg-muted disabled:opacity-40"
          >
            Далі <ChevronRight className="h-4 w-4" />
          </button>
        </div>
      </div>
    </div>
  );
}
