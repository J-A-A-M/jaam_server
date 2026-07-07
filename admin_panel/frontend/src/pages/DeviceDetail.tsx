import { useQuery, keepPreviousData } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { MapContainer, Marker, TileLayer } from "react-leaflet";
import { ArrowLeft, ChevronLeft, ChevronRight, FlaskConical } from "lucide-react";
import { api, type Device } from "@/lib/api";
import { Badge, Card, CardBody, CardHeader, CardTitle, RelativeTime, Spinner } from "@/components/ui";
import { useTheme } from "@/components/ThemeContext";
import { fmtDateTime, fmtDuration } from "@/lib/utils";

function LiveDuration({ startedAt }: { startedAt: string }) {
  const [sec, setSec] = useState(() => Math.floor((Date.now() - new Date(startedAt).getTime()) / 1000));
  useEffect(() => {
    const id = setInterval(() => setSec(Math.floor((Date.now() - new Date(startedAt).getTime()) / 1000)), 1000);
    return () => clearInterval(id);
  }, [startedAt]);
  const h = Math.floor(sec / 3600);
  const m = Math.floor((sec % 3600) / 60);
  const s = sec % 60;
  if (h > 0) return <>{h}г {m}хв</>;
  if (m > 0) return <>{m}хв {String(s).padStart(2, "0")}с</>;
  return <>{s}с</>;
}

const EVENT_LABEL: Record<string, string> = {
  online: "З'явилась онлайн",
  offline: "Пішла в офлайн",
  firmware_change: "Оновлення прошивки",
  firmware_id_change: "Зміна ID мапи",
  geo_change: "Зміна локації",
  ip_change: "Зміна IP",
  first_seen: "Перша поява",
};

function eventDetail(type: string, details: string | null): string | null {
  if (!details) return null;
  try {
    const d = JSON.parse(details) as Record<string, string | null>;
    switch (type) {
      case "first_seen":      return d.firmware ?? null;
      case "online":          return d.server ?? null;
      case "firmware_change":    return d.from && d.to ? `${d.from} → ${d.to}` : null;
      case "firmware_id_change": return `${d.from ?? "—"} → ${d.to ?? "—"}`;
      case "geo_change":         return d.from && d.to ? `${d.from} → ${d.to}` : null;
      case "ip_change":       return d.from && d.to ? `${d.from} → ${d.to}` : null;
      default:                return null;
    }
  } catch {
    return null;
  }
}

const _countryNames = new Intl.DisplayNames(["en"], { type: "region" });
function countryName(code: string | null): string | null {
  if (!code) return null;
  try { return _countryNames.of(code) ?? code; } catch { return code; }
}

function Field({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div>
      <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{label}</div>
      <div className="mt-0.5 break-all text-sm text-foreground">{value ?? "—"}</div>
    </div>
  );
}

function SameIpCard({ ip, devices }: { ip: string; devices: Device[] }) {
  return (
    <Card className="overflow-hidden">
      <CardHeader>
        <CardTitle>
          Інші мапи з IP <span className="font-mono text-primary">{ip}</span>
          <span className="ml-2 text-sm font-normal text-muted-foreground">({devices.length})</span>
        </CardTitle>
      </CardHeader>
      <CardBody className="p-0">
        <div className="overflow-x-auto">
          <table className="w-full text-sm [&_tbody_td]:align-middle">
            <thead>
              <tr className="border-b border-border/[0.1] text-left">
                <th className="px-4 py-2 text-xs font-medium text-muted-foreground">Статус</th>
                <th className="px-4 py-2 text-xs font-medium text-muted-foreground">Chip ID</th>
                <th className="hidden px-4 py-2 text-xs font-medium text-muted-foreground sm:table-cell">Тип</th>
                <th className="hidden px-4 py-2 text-xs font-medium text-muted-foreground md:table-cell">Прошивка</th>
                <th className="hidden px-4 py-2 text-xs font-medium text-muted-foreground lg:table-cell">Місто</th>
                <th className="px-4 py-2 text-xs font-medium text-muted-foreground">Остання активність</th>
              </tr>
            </thead>
            <tbody>
              {devices.map((dev) => (
                <tr key={dev.chip_id} className="border-b border-border/[0.07] transition hover:bg-muted/40 last:border-0">
                  <td className="px-4 py-2.5">
                    <Badge variant={dev.is_online ? "online" : "offline"}>{dev.is_online ? "online" : "offline"}</Badge>
                  </td>
                  <td className="px-4 py-2.5">
                    <Link to={`/devices/${encodeURIComponent(dev.chip_id)}`} className="font-mono text-xs text-primary hover:underline sm:text-sm">
                      {dev.chip_id}
                    </Link>
                    {dev.firmware_id && <div className="font-mono text-[11px] text-muted-foreground">{dev.firmware_id}</div>}
                  </td>
                  <td className="hidden px-4 py-2.5 sm:table-cell">
                    {dev.is_jaam ? (
                      <span className="inline-flex items-center gap-1 rounded-full border border-primary/30 bg-primary/10 px-2 py-0.5 text-xs font-medium text-primary" title={dev.customer_info ?? undefined}>
                        {dev.is_prototype && <FlaskConical className="h-3 w-3 shrink-0" />}
                        {dev.hw_version ?? "JAAM"}
                      </span>
                    ) : (
                      <span className="inline-flex items-center rounded-full border border-border/[0.15] bg-muted px-2 py-0.5 text-xs font-medium text-muted-foreground">
                        SELF
                      </span>
                    )}
                  </td>
                  <td className="hidden px-4 py-2.5 font-mono text-xs text-muted-foreground md:table-cell">{dev.firmware ?? "—"}</td>
                  <td className="hidden px-4 py-2.5 text-muted-foreground lg:table-cell">{dev.city ?? "—"}</td>
                  <td className="px-4 py-2.5 text-xs text-muted-foreground"><RelativeTime ts={dev.last_seen} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </CardBody>
    </Card>
  );
}

const _PAGE_SIZE = 20;

export default function DeviceDetail() {
  const { chipId } = useParams();
  const navigate = useNavigate();
  const { theme } = useTheme();
  const [sessionsPage, setSessionsPage] = useState(1);
  const [eventsPage, setEventsPage] = useState(1);

  useEffect(() => {
    setSessionsPage(1);
    setEventsPage(1);
  }, [chipId]);

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["device", chipId, sessionsPage, eventsPage],
    queryFn: () => api.device(chipId!, sessionsPage, eventsPage),
    refetchInterval: 15000,
    placeholderData: keepPreviousData,
  });

  const { data: sameIpData } = useQuery({
    queryKey: ["device-same-ip", chipId],
    queryFn: () => api.sameIp(chipId!),
    enabled: !!data?.device.last_ip,
    refetchInterval: 30000,
  });

  if (isLoading)
    return (
      <div className="flex items-center justify-center py-40">
        <Spinner className="h-8 w-8" />
      </div>
    );

  if (isError || !data)
    return (
      <div className="space-y-4 p-4 sm:p-6">
        <button onClick={() => navigate(-1)} className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
          <ArrowLeft className="h-4 w-4" /> До списку
        </button>
        <div className="rounded-lg border border-border/[0.1] bg-card px-6 py-12 text-center text-muted-foreground">
          {(error as { status?: number })?.status === 404
            ? "Мапу не знайдено"
            : "Не вдалося завантажити дані"}
        </div>
      </div>
    );

  const d = data.device;
  const tileUrl = theme === "dark"
    ? "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
    : "https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png";

  return (
    <div className="space-y-4 p-4 sm:space-y-6 sm:p-6">
      <button onClick={() => navigate(-1)} className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
        <ArrowLeft className="h-4 w-4" /> До списку
      </button>

      <div className="flex flex-wrap items-center gap-2 sm:gap-3">
        <h1 className="break-all font-mono text-xl font-bold sm:text-2xl">{d.chip_id}</h1>
        <Badge variant={!d.ever_seen ? "unseen" : d.is_online ? "online" : "offline"}>
          {!d.ever_seen ? "unseen" : d.is_online ? "online" : "offline"}
        </Badge>
      </div>

      {d.is_jaam && (
        <Card>
          <CardHeader><CardTitle>Дані реєстру JAAM</CardTitle></CardHeader>
          <CardBody className="grid grid-cols-2 gap-4 sm:grid-cols-4">
            {d.map_id && <Field label="Мітка" value={<span className="font-mono">{d.map_id}</span>} />}
            <Field label="Тип" value={d.hw_version} />
            <Field label="Прототип" value={d.is_prototype ? "так" : "ні"} />
            {d.order_number && <Field label="№ замовлення" value={d.order_number} />}
            <Field label="Клієнт" value={d.customer_info} />
          </CardBody>
        </Card>
      )}

      <div className="grid gap-4 sm:gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader><CardTitle>Інформація</CardTitle></CardHeader>
          <CardBody className="grid grid-cols-2 gap-4 sm:grid-cols-3">
            <Field label="Прошивка" value={d.ever_seen ? <span className="font-mono">{d.firmware}</span> : null} />
            <Field label="ID" value={d.ever_seen ? <span className="font-mono">{d.firmware_id}</span> : null} />
            <Field label="HW" value={d.ever_seen ? d.hw_type : null} />
            <Field label="Сервер" value={d.ever_seen ? d.last_server : null} />
            <Field label="IP" value={d.ever_seen ? <span className="font-mono">{d.last_ip}</span> : null} />
            <Field label="Місто" value={d.ever_seen ? d.city : null} />
            <Field label="Регіон" value={d.ever_seen ? d.region : null} />
            <Field label="Країна" value={d.ever_seen ? countryName(d.country) : null} />
            <Field label="Провайдер" value={d.ever_seen ? d.org : null} />
            <Field label="Latency" value={d.ever_seen && d.latency != null && d.latency >= 0 ? `${d.latency} мс` : null} />
            <Field label="Перша поява" value={d.ever_seen ? fmtDateTime(d.first_seen) : null} />
            <Field label="Остання активність" value={d.ever_seen ? <RelativeTime ts={d.last_seen} /> : null} />
            <Field label="Захищене з'єднання" value={d.ever_seen ? (d.secure_connection ? "так" : "ні") : null} />
          </CardBody>
        </Card>

        <Card className="overflow-hidden">
          <CardHeader><CardTitle>Локація</CardTitle></CardHeader>
          <CardBody className="p-0">
            {d.lat != null && d.lon != null ? (
              <div className="isolate h-[220px] sm:h-[260px]">
                <MapContainer center={[d.lat, d.lon]} zoom={9} className="h-full w-full" scrollWheelZoom={false}>
                  <TileLayer url={tileUrl} attribution="© OpenStreetMap" />
                  <Marker position={[d.lat, d.lon]} />
                </MapContainer>
              </div>
            ) : (
              <div className="flex h-[220px] items-center justify-center text-sm text-muted-foreground">
                Координати невідомі
              </div>
            )}
          </CardBody>
        </Card>
      </div>

      {sameIpData && sameIpData.length > 0 && (
        <SameIpCard ip={d.last_ip!} devices={sameIpData} />
      )}

      <div className="grid gap-4 sm:gap-6 lg:grid-cols-2">
        <Card className="overflow-hidden">
          <CardHeader><CardTitle>Сесії ({data.sessions_total})</CardTitle></CardHeader>
          <CardBody className="space-y-2">
            {data.sessions.length === 0 && <div className="text-sm text-muted-foreground">Немає сесій</div>}
            {data.sessions.map((s) => (
              <div key={s.id} className="flex items-center justify-between border-b border-border/[0.07] pb-2 text-sm last:border-0">
                <div className="flex-1 min-w-0">
                  <div className="truncate text-foreground">{fmtDateTime(s.started_at)}</div>
                  <div className="truncate text-xs text-muted-foreground">
                    {s.ended_at ? `завершено ${fmtDateTime(s.ended_at)}` : "триває"} · {s.server_name ?? "—"}
                  </div>
                  {s.ip && <div className="truncate font-mono text-xs text-muted-foreground">{s.ip}</div>}
                </div>
                <Badge variant={s.ended_at ? "offline" : "online"} className="ml-2 shrink-0 font-mono">
                  {s.ended_at ? fmtDuration(s.duration_sec) : <LiveDuration startedAt={s.started_at} />}
                </Badge>
              </div>
            ))}
            {data.sessions_total > _PAGE_SIZE && (
              <div className="flex items-center justify-between border-t border-border/[0.07] pt-2 text-xs text-muted-foreground">
                <span>{Math.min((sessionsPage - 1) * _PAGE_SIZE + 1, data.sessions_total)}–{Math.min(sessionsPage * _PAGE_SIZE, data.sessions_total)} з {data.sessions_total}</span>
                <div className="flex gap-1">
                  <button disabled={sessionsPage <= 1} onClick={() => setSessionsPage(p => p - 1)}
                    className="flex items-center gap-0.5 rounded border border-border/[0.1] px-2 py-1 transition hover:bg-muted hover:text-foreground disabled:opacity-40">
                    <ChevronLeft className="h-3 w-3" /><span className="hidden sm:inline"> Назад</span>
                  </button>
                  <button disabled={sessionsPage >= Math.ceil(data.sessions_total / _PAGE_SIZE)} onClick={() => setSessionsPage(p => p + 1)}
                    className="flex items-center gap-0.5 rounded border border-border/[0.1] px-2 py-1 transition hover:bg-muted hover:text-foreground disabled:opacity-40">
                    <span className="hidden sm:inline">Далі </span><ChevronRight className="h-3 w-3" />
                  </button>
                </div>
              </div>
            )}
          </CardBody>
        </Card>

        <Card className="overflow-hidden">
          <CardHeader><CardTitle>Події ({data.events_total})</CardTitle></CardHeader>
          <CardBody className="space-y-2">
            {data.events.length === 0 && <div className="text-sm text-muted-foreground">Немає подій</div>}
            {data.events.map((e) => {
              const detail = eventDetail(e.type, e.details);
              return (
                <div key={e.id} className="flex items-start justify-between border-b border-border/[0.07] pb-2 text-sm last:border-0">
                  <div className="flex-1 min-w-0">
                    <div className="truncate text-foreground">{EVENT_LABEL[e.type] ?? e.type}</div>
                    {detail && <div className="truncate font-mono text-xs text-muted-foreground">{detail}</div>}
                  </div>
                  <RelativeTime ts={e.ts} className="ml-2 shrink-0 text-xs text-muted-foreground" />
                </div>
              );
            })}
            {data.events_total > _PAGE_SIZE && (
              <div className="flex items-center justify-between border-t border-border/[0.07] pt-2 text-xs text-muted-foreground">
                <span>{Math.min((eventsPage - 1) * _PAGE_SIZE + 1, data.events_total)}–{Math.min(eventsPage * _PAGE_SIZE, data.events_total)} з {data.events_total}</span>
                <div className="flex gap-1">
                  <button disabled={eventsPage <= 1} onClick={() => setEventsPage(p => p - 1)}
                    className="flex items-center gap-0.5 rounded border border-border/[0.1] px-2 py-1 transition hover:bg-muted hover:text-foreground disabled:opacity-40">
                    <ChevronLeft className="h-3 w-3" /><span className="hidden sm:inline"> Назад</span>
                  </button>
                  <button disabled={eventsPage >= Math.ceil(data.events_total / _PAGE_SIZE)} onClick={() => setEventsPage(p => p + 1)}
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
