import { useQuery, keepPreviousData } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { MapContainer, Marker, TileLayer } from "react-leaflet";
import { ArrowLeft, ChevronLeft, ChevronRight } from "lucide-react";
import { api } from "@/lib/api";
import { Badge, Card, CardBody, CardHeader, CardTitle, Spinner } from "@/components/ui";
import { useTheme } from "@/components/ThemeContext";
import { fmtDateTime, fmtDuration, timeAgo } from "@/lib/utils";

function LiveDuration({ startedAt }: { startedAt: string }) {
  const [sec, setSec] = useState(() => Math.floor((Date.now() - new Date(startedAt).getTime()) / 1000));
  useEffect(() => {
    const id = setInterval(() => setSec(Math.floor((Date.now() - new Date(startedAt).getTime()) / 1000)), 1000);
    return () => clearInterval(id);
  }, [startedAt]);
  const h = Math.floor(sec / 3600);
  const m = Math.floor((sec % 3600) / 60);
  const s = sec % 60;
  if (h > 0) return <>{h}г {m}хв {String(s).padStart(2, "0")}с</>;
  if (m > 0) return <>{m}хв {String(s).padStart(2, "0")}с</>;
  return <>{s}с</>;
}

const EVENT_LABEL: Record<string, string> = {
  online: "З'явилась онлайн",
  offline: "Пішла в офлайн",
  firmware_change: "Оновлення прошивки",
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
      case "firmware_change": return d.from && d.to ? `${d.from} → ${d.to}` : null;
      case "geo_change":      return d.from && d.to ? `${d.from} → ${d.to}` : null;
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
    : "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png";

  return (
    <div className="space-y-4 p-4 sm:space-y-6 sm:p-6">
      <button onClick={() => navigate(-1)} className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
        <ArrowLeft className="h-4 w-4" /> До списку
      </button>

      <div className="flex flex-wrap items-center gap-2 sm:gap-3">
        <h1 className="break-all font-mono text-xl font-bold sm:text-2xl">{d.chip_id}</h1>
        <Badge variant={d.is_online ? "online" : "offline"}>{d.is_online ? "online" : "offline"}</Badge>
      </div>

      {d.is_jaam && (
        <Card>
          <CardHeader><CardTitle>Дані реєстру JAAM</CardTitle></CardHeader>
          <CardBody className="grid grid-cols-2 gap-4 sm:grid-cols-4">
            {d.map_id && <Field label="ID" value={<span className="font-mono">{d.map_id}</span>} />}
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
            <Field label="Прошивка" value={<span className="font-mono">{d.firmware}</span>} />
            <Field label="ID" value={<span className="font-mono">{d.firmware_id}</span>} />
            <Field label="HW" value={d.hw_type} />
            <Field label="Сервер" value={d.last_server} />
            <Field label="IP" value={<span className="font-mono">{d.last_ip}</span>} />
            <Field label="Місто" value={d.city} />
            <Field label="Регіон" value={d.region} />
            <Field label="Країна" value={countryName(d.country)} />
            <Field label="Провайдер" value={d.org} />
            <Field label="Latency" value={d.latency != null && d.latency >= 0 ? `${d.latency} мс` : "—"} />
            <Field label="Перша поява" value={fmtDateTime(d.first_seen)} />
            <Field label="Остання активність" value={timeAgo(d.last_seen)} />
            <Field label="Захищене з'єднання" value={d.secure_connection ? "так" : "ні"} />
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

      <div className="grid gap-4 sm:gap-6 lg:grid-cols-2">
        <Card>
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
                    <ChevronLeft className="h-3 w-3" /> Назад
                  </button>
                  <button disabled={sessionsPage >= Math.ceil(data.sessions_total / _PAGE_SIZE)} onClick={() => setSessionsPage(p => p + 1)}
                    className="flex items-center gap-0.5 rounded border border-border/[0.1] px-2 py-1 transition hover:bg-muted hover:text-foreground disabled:opacity-40">
                    Далі <ChevronRight className="h-3 w-3" />
                  </button>
                </div>
              </div>
            )}
          </CardBody>
        </Card>

        <Card>
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
                  <span className="ml-2 shrink-0 text-xs text-muted-foreground" title={fmtDateTime(e.ts)}>{timeAgo(e.ts)}</span>
                </div>
              );
            })}
            {data.events_total > _PAGE_SIZE && (
              <div className="flex items-center justify-between border-t border-border/[0.07] pt-2 text-xs text-muted-foreground">
                <span>{Math.min((eventsPage - 1) * _PAGE_SIZE + 1, data.events_total)}–{Math.min(eventsPage * _PAGE_SIZE, data.events_total)} з {data.events_total}</span>
                <div className="flex gap-1">
                  <button disabled={eventsPage <= 1} onClick={() => setEventsPage(p => p - 1)}
                    className="flex items-center gap-0.5 rounded border border-border/[0.1] px-2 py-1 transition hover:bg-muted hover:text-foreground disabled:opacity-40">
                    <ChevronLeft className="h-3 w-3" /> Назад
                  </button>
                  <button disabled={eventsPage >= Math.ceil(data.events_total / _PAGE_SIZE)} onClick={() => setEventsPage(p => p + 1)}
                    className="flex items-center gap-0.5 rounded border border-border/[0.1] px-2 py-1 transition hover:bg-muted hover:text-foreground disabled:opacity-40">
                    Далі <ChevronRight className="h-3 w-3" />
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
