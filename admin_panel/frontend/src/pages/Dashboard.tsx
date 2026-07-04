import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Activity, Cpu, Clock, PlusCircle } from "lucide-react";
import { api, type DeviceEvent } from "@/lib/api";
import { Card, CardBody, CardHeader, CardTitle, Spinner, Stat } from "@/components/ui";
import { fmtDateTime, timeAgo } from "@/lib/utils";

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

const chartAxis = { stroke: "#48526A", fontSize: 10, fontFamily: "'JetBrains Mono', monospace" };
const tooltipStyle = {
  background: "#0B0D14",
  border: "1px solid rgba(255,255,255,0.08)",
  borderRadius: 4,
  fontSize: 11,
  fontFamily: "'JetBrains Mono', monospace",
  color: "#C4CFDF",
};

const EVENT_LABEL: Record<string, string> = {
  online: "з'явилась",
  offline: "зникла",
  firmware_change: "оновлення прошивки",
  geo_change: "зміна локації",
  ip_change: "зміна IP",
  first_seen: "нова мапа",
};

export default function Dashboard() {
  const stream = useStream();
  const { data, isLoading } = useQuery({
    queryKey: ["overview"],
    queryFn: api.overview,
    refetchInterval: 30000,
  });

  if (isLoading || !data)
    return (
      <div className="flex h-full items-center justify-center py-40">
        <Spinner className="h-8 w-8" />
      </div>
    );

  const onlineNow = stream?.online_now ?? data.online_now;
  const totalReg = stream?.total_registered ?? data.total_registered;

  const trend = data.online_trend.map((p) => ({
    t: new Date(p.ts).toLocaleTimeString("uk-UA", { hour: "2-digit", minute: "2-digit" }),
    online: p.online,
  }));

  return (
    <div className="space-y-6 p-6">
      <div>
        <h1 className="text-2xl font-bold">Дашборд</h1>
        <p className="text-sm text-muted-foreground">Загальний стан парку мап</p>
      </div>

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Stat
          label="Онлайн зараз"
          value={<span className="text-primary">{onlineNow}</span>}
          hint={<span className="inline-flex items-center gap-1"><Activity className="h-3 w-3" /> JAAM {data.jaam_online} · самозбірки {data.self_online}</span>}
        />
        <Stat label="Усього бачено" value={totalReg} hint={<span className="inline-flex items-center gap-1"><Cpu className="h-3 w-3" /> у реєстрі JAAM {data.registry_total}</span>} />
        <Stat label="Активні за 24 год" value={data.unique_24h} hint={<span className="inline-flex items-center gap-1"><Clock className="h-3 w-3" /> медіана {data.median_online}</span>} />
        <Stat label="Нові за 24 год" value={data.new_24h} hint={<span className="inline-flex items-center gap-1"><PlusCircle className="h-3 w-3" /> вперше побачені</span>} />
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Онлайн за останні 24 години</CardTitle>
        </CardHeader>
        <CardBody>
          <ResponsiveContainer width="100%" height={240}>
            <AreaChart data={trend}>
              <defs>
                <linearGradient id="g" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#F59E0B" stopOpacity={0.3} />
                  <stop offset="100%" stopColor="#F59E0B" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
              <XAxis dataKey="t" {...chartAxis} minTickGap={40} />
              <YAxis {...chartAxis} allowDecimals={false} width={30} />
              <Tooltip contentStyle={tooltipStyle} />
              <Area type="monotone" dataKey="online" stroke="#F59E0B" fill="url(#g)" strokeWidth={1.5} dot={false} />
            </AreaChart>
          </ResponsiveContainer>
        </CardBody>
      </Card>

      <div className="grid gap-6 lg:grid-cols-2">
        <DistroChart title="Версії прошивок" items={data.by_firmware} />
        <DistroChart title="Топ регіонів" items={data.by_region} />
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <DistroChart title="Тривалість онлайн-сесій" items={data.duration_histogram} hideEmpty />
        <Card>
          <CardHeader>
            <CardTitle>Останні події</CardTitle>
          </CardHeader>
          <CardBody className="space-y-2">
            {(stream?.events ?? []).length === 0 && (
              <div className="py-6 text-center text-sm text-muted-foreground">Подій ще немає</div>
            )}
            {(stream?.events ?? []).map((e) => (
              <div key={e.id} className="flex items-center justify-between border-b border-border/50 pb-2 text-sm last:border-0">
                <div className="flex items-center gap-2">
                  <span
                    className={
                      e.type === "offline"
                        ? "h-2 w-2 rounded-full bg-muted-foreground"
                        : "h-2 w-2 rounded-full bg-success"
                    }
                  />
                  <span className="font-mono text-xs text-muted-foreground">{e.chip_id}</span>
                  <span>{EVENT_LABEL[e.type] ?? e.type}</span>
                </div>
                <span className="text-xs text-muted-foreground" title={fmtDateTime(e.ts)}>
                  {timeAgo(e.ts)}
                </span>
              </div>
            ))}
          </CardBody>
        </Card>
      </div>
    </div>
  );
}

function DistroChart({
  title,
  items,
  hideEmpty,
}: {
  title: string;
  items: { label: string; count: number }[];
  hideEmpty?: boolean;
}) {
  const data = hideEmpty ? items.filter((i) => i.count > 0) : items;
  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
      </CardHeader>
      <CardBody>
        {data.length === 0 ? (
          <div className="py-6 text-center text-sm text-muted-foreground">Немає даних</div>
        ) : (
          <ResponsiveContainer width="100%" height={Math.max(200, data.length * 28)}>
            <BarChart data={data} layout="vertical" margin={{ left: 8 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="hsl(215 20% 18%)" horizontal={false} />
              <XAxis type="number" {...chartAxis} allowDecimals={false} />
              <YAxis type="category" dataKey="label" {...chartAxis} width={110} />
              <Tooltip contentStyle={tooltipStyle} cursor={{ fill: "hsl(217 20% 16%)" }} />
              <Bar dataKey="count" fill="hsl(199 89% 52%)" radius={[0, 4, 4, 0]} />
            </BarChart>
          </ResponsiveContainer>
        )}
      </CardBody>
    </Card>
  );
}
