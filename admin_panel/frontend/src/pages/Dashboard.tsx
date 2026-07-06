import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useQuery, keepPreviousData } from "@tanstack/react-query";
import {
  Area, AreaChart, Bar, BarChart, CartesianGrid,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { Activity, Cpu, Clock, PlusCircle, ChevronLeft, ChevronRight } from "lucide-react";
import { api, type DeviceEvent } from "@/lib/api";
import { Card, CardBody, CardHeader, CardTitle, Spinner, Stat } from "@/components/ui";
import { useTheme } from "@/components/ThemeContext";
import { fmtDateTime, timeAgo } from "@/lib/utils";

const _EVENTS_PAGE_SIZE = 20;

interface StreamData {
  online_now: number;
  total_registered: number;
  events: DeviceEvent[];
}

function useStream(): StreamData | null {
  const [data, setData] = useState<StreamData | null>(null);
  useEffect(() => {
    const es = new EventSource("/api/stream", { withCredentials: true });
    es.onmessage = (e) => setData(JSON.parse(e.data));
    return () => es.close();
  }, []);
  return data;
}

const EVENT_LABEL: Record<string, string> = {
  online: "з'явилась",
  offline: "зникла",
  firmware_change: "оновлення прошивки",
  geo_change: "зміна локації",
  ip_change: "зміна IP",
  first_seen: "нова мапа",
};

function useChartPalette() {
  const { theme } = useTheme();
  const isDark = theme === "dark";
  return {
    axis:    { stroke: isDark ? "#5C6A80" : "#94A3B8", fontSize: 10, fontFamily: "'JetBrains Mono', monospace" },
    tooltip: {
      background: isDark ? "#0B0D14" : "#FFFFFF",
      border: `1px solid ${isDark ? "rgba(255,255,255,0.08)" : "rgba(0,0,0,0.08)"}`,
      borderRadius: 4, fontSize: 11,
      fontFamily: "'JetBrains Mono', monospace",
      color: isDark ? "#DCE4F0" : "#0F172A",
    },
    primary:  isDark ? "#F59E0B" : "#D97706",
    accent:   "#22D3EE",
    gridArea: isDark ? "rgba(255,255,255,0.05)" : "rgba(0,0,0,0.05)",
    gridBar:  isDark ? "rgba(255,255,255,0.06)" : "rgba(0,0,0,0.06)",
    cursor:   isDark ? "rgba(255,255,255,0.04)" : "rgba(0,0,0,0.04)",
  };
}

export default function Dashboard() {
  const stream = useStream();
  const palette = useChartPalette();
  const [eventsPage, setEventsPage] = useState(1);

  const { data, isLoading } = useQuery({
    queryKey: ["overview"],
    queryFn: api.overview,
    refetchInterval: 30000,
  });

  const { data: eventsData } = useQuery({
    queryKey: ["dashboard-events", eventsPage],
    queryFn: () => api.events(eventsPage, _EVENTS_PAGE_SIZE),
    refetchInterval: 15000,
    placeholderData: keepPreviousData,
  });

  if (isLoading || !data)
    return (
      <div className="flex h-full items-center justify-center py-40">
        <Spinner className="h-8 w-8" />
      </div>
    );

  const onlineNow = stream?.online_now ?? data.online_now;
  const totalReg  = stream?.total_registered ?? data.total_registered;

  const trend = data.online_trend.map((p) => ({
    t: new Date(p.ts).toLocaleTimeString("uk-UA", { hour: "2-digit", minute: "2-digit" }),
    online: p.online,
  }));

  const fmtDay = (iso: string) => {
    const d = new Date(iso + "T00:00:00Z");
    return `${String(d.getUTCDate()).padStart(2, "0")}.${String(d.getUTCMonth() + 1).padStart(2, "0")}`;
  };
  const newPerDay  = data.new_per_day.map((p)    => ({ day: fmtDay(p.date), count: p.count }));
  const activePerDay = data.active_per_day.map((p) => ({ day: fmtDay(p.date), count: p.count }));

  return (
    <div className="space-y-4 p-4 sm:space-y-6 sm:p-6">
      <div>
        <h1 className="text-xl font-bold sm:text-2xl">Дашборд</h1>
        <p className="text-sm text-muted-foreground">Загальний стан парку мап</p>
      </div>

      <div className="grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-4">
        <Stat
          label="Онлайн зараз"
          value={<span className="text-primary">{onlineNow}</span>}
          hint={<span className="inline-flex items-center gap-1"><Activity className="h-3 w-3" /> JAAM {data.jaam_online} · самозбірки {data.self_online}</span>}
        />
        <Stat label="Усього мап" value={totalReg}
          hint={<span className="inline-flex items-center gap-1"><Cpu className="h-3 w-3" /> у реєстрі JAAM {data.registry_total}</span>} />
        <Stat label="Активні за 24 год" value={data.unique_24h}
          hint={<span className="inline-flex items-center gap-1"><Clock className="h-3 w-3" /> медіана {data.median_online}</span>} />
        <Stat label="Нові за 24 год" value={data.new_24h}
          hint={<span className="inline-flex items-center gap-1"><PlusCircle className="h-3 w-3" /> вперше побачені</span>} />
      </div>

      <Card>
        <CardHeader><CardTitle>Онлайн за останні 24 години</CardTitle></CardHeader>
        <CardBody>
          <ResponsiveContainer width="100%" height={200}>
            <AreaChart data={trend}>
              <defs>
                <linearGradient id="g" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={palette.primary} stopOpacity={0.3} />
                  <stop offset="100%" stopColor={palette.primary} stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke={palette.gridArea} />
              <XAxis dataKey="t" {...palette.axis} minTickGap={40} />
              <YAxis {...palette.axis} allowDecimals={false} width={28} domain={[(min: number) => Math.max(0, min - 1), (max: number) => max + 1]} />
              <Tooltip contentStyle={palette.tooltip} />
              <Area type="monotone" dataKey="online" stroke={palette.primary} fill="url(#g)" strokeWidth={1.5} dot={false} />
            </AreaChart>
          </ResponsiveContainer>
        </CardBody>
      </Card>

      <div className="grid gap-4 sm:gap-6 lg:grid-cols-2">
        <MonthChart title="Нові мапи за 30 днів" data={newPerDay} color={palette.accent} />
        <MonthChart title="Активні мапи за 30 днів" data={activePerDay} color={palette.primary} />
      </div>

      <div className="grid gap-4 sm:gap-6 lg:grid-cols-2">
        <DistroChart title="Версії прошивок" items={data.by_firmware} />
        <DistroChart title="Типи HW" items={data.by_hw} />
      </div>

      <div className="grid gap-4 sm:gap-6 lg:grid-cols-3">
        <DistroChart title="Топ країн" items={data.by_country} labelFmt={countryLabel} />
        <DistroChart title="Топ регіонів" items={data.by_region} />
        <DistroChart title="Топ міст" items={data.by_city} />
      </div>

      <div className="grid gap-4 sm:gap-6 lg:grid-cols-2">
        <DistroChart title="Тривалість онлайн-сесій" items={data.duration_histogram} hideEmpty horizontal />
        <Card className="overflow-hidden">
          <CardHeader><CardTitle>Останні події {eventsData ? `(${eventsData.total})` : ""}</CardTitle></CardHeader>
          <CardBody className="space-y-2">
            {(!eventsData || eventsData.items.length === 0) && (
              <div className="py-6 text-center text-sm text-muted-foreground">Подій ще немає</div>
            )}
            {(eventsData?.items ?? []).map((e) => (
              <Link
                key={e.id}
                to={e.chip_id ? `/devices/${encodeURIComponent(e.chip_id)}` : "#"}
                className="flex items-center justify-between border-b border-border/[0.07] pb-2 text-sm last:border-0 hover:bg-muted/40 -mx-4 px-4 rounded transition-colors"
              >
                <div className="flex flex-1 min-w-0 items-center gap-2 overflow-hidden">
                  <span className={e.type === "offline" ? "h-2 w-2 shrink-0 rounded-full bg-muted-foreground" : "h-2 w-2 shrink-0 rounded-full bg-success"} />
                  <span className="font-mono text-xs text-muted-foreground truncate">{e.chip_id}</span>
                  <span className="shrink-0">{EVENT_LABEL[e.type] ?? e.type}</span>
                </div>
                <span className="ml-2 shrink-0 text-xs text-muted-foreground" title={fmtDateTime(e.ts)}>
                  {timeAgo(e.ts)}
                </span>
              </Link>
            ))}
            {eventsData && eventsData.total > _EVENTS_PAGE_SIZE && (
              <div className="flex items-center justify-between border-t border-border/[0.07] pt-2 text-xs text-muted-foreground">
                <span>{Math.min((eventsPage - 1) * _EVENTS_PAGE_SIZE + 1, eventsData.total)}–{Math.min(eventsPage * _EVENTS_PAGE_SIZE, eventsData.total)} з {eventsData.total}</span>
                <div className="flex gap-1">
                  <button disabled={eventsPage <= 1} onClick={() => setEventsPage(p => p - 1)}
                    className="flex items-center gap-0.5 rounded border border-border/[0.1] px-2 py-1 transition hover:bg-muted hover:text-foreground disabled:opacity-40">
                    <ChevronLeft className="h-3 w-3" /><span className="hidden sm:inline"> Назад</span>
                  </button>
                  <button disabled={eventsPage >= Math.ceil(eventsData.total / _EVENTS_PAGE_SIZE)} onClick={() => setEventsPage(p => p + 1)}
                    className="flex items-center gap-0.5 rounded border border-border/[0.1] px-2 py-1 transition hover:bg-muted hover:text-foreground disabled:opacity-40">
                    <span className="hidden sm:inline">Далі </span><ChevronRight className="h-3 w-3" />
                  </button>
                </div>
              </div>
            )}
          </CardBody>
        </Card>
      </div>
    </div>
  );
}

const _displayNames = new Intl.DisplayNames(["en"], { type: "region" });
function countryLabel(code: string): string {
  try { return _displayNames.of(code) ?? code; } catch { return code; }
}

function MonthChart({ title, data, color }: { title: string; data: { day: string; count: number }[]; color: string }) {
  const palette = useChartPalette();
  return (
    <Card>
      <CardHeader><CardTitle>{title}</CardTitle></CardHeader>
      <CardBody>
        <ResponsiveContainer width="100%" height={160}>
          <BarChart data={data} margin={{ left: 0, right: 4 }}>
            <CartesianGrid strokeDasharray="3 3" stroke={palette.gridBar} vertical={false} />
            <XAxis dataKey="day" {...palette.axis} minTickGap={24} />
            <YAxis {...palette.axis} allowDecimals={false} width={28} />
            <Tooltip contentStyle={palette.tooltip} cursor={{ fill: palette.cursor }} />
            <Bar dataKey="count" fill={color} radius={[3, 3, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </CardBody>
    </Card>
  );
}

function DistroChart({ title, items, hideEmpty, labelFmt, horizontal }: { title: string; items: { label: string; count: number }[]; hideEmpty?: boolean; labelFmt?: (l: string) => string; horizontal?: boolean }) {
  const palette = useChartPalette();
  const raw = hideEmpty ? items.filter((i) => i.count > 0) : items;
  const data = labelFmt ? raw.map((i) => ({ ...i, label: labelFmt(i.label) })) : raw;
  return (
    <Card>
      <CardHeader><CardTitle>{title}</CardTitle></CardHeader>
      <CardBody>
        {data.length === 0 ? (
          <div className="py-6 text-center text-sm text-muted-foreground">Немає даних</div>
        ) : horizontal ? (
          <ResponsiveContainer width="100%" height={160}>
            <BarChart data={data} margin={{ left: 0, right: 4 }}>
              <CartesianGrid strokeDasharray="3 3" stroke={palette.gridBar} vertical={false} />
              <XAxis dataKey="label" {...palette.axis} minTickGap={20} />
              <YAxis {...palette.axis} allowDecimals={false} width={28} />
              <Tooltip contentStyle={palette.tooltip} cursor={{ fill: palette.cursor }} />
              <Bar dataKey="count" fill={palette.accent} radius={[3, 3, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        ) : (
          <ResponsiveContainer width="100%" height={Math.max(160, data.length * 26)}>
            <BarChart data={data} layout="vertical" margin={{ left: 4 }}>
              <CartesianGrid strokeDasharray="3 3" stroke={palette.gridBar} horizontal={false} />
              <XAxis type="number" {...palette.axis} allowDecimals={false} />
              <YAxis type="category" dataKey="label" {...palette.axis} width={100} />
              <Tooltip contentStyle={palette.tooltip} cursor={{ fill: palette.cursor }} />
              <Bar dataKey="count" fill={palette.accent} radius={[0, 4, 4, 0]} />
            </BarChart>
          </ResponsiveContainer>
        )}
      </CardBody>
    </Card>
  );
}
