import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { MapContainer, Marker, TileLayer } from "react-leaflet";
import { ArrowLeft } from "lucide-react";
import { api } from "@/lib/api";
import { Badge, Card, CardBody, CardHeader, CardTitle, Spinner } from "@/components/ui";
import { useTheme } from "@/components/ThemeContext";
import { fmtDateTime, fmtDuration, timeAgo } from "@/lib/utils";

const EVENT_LABEL: Record<string, string> = {
  online: "З'явилась онлайн",
  offline: "Пішла в офлайн",
  firmware_change: "Оновлення прошивки",
  geo_change: "Зміна локації",
  ip_change: "Зміна IP",
  first_seen: "Перша поява",
};

function Field({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div>
      <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{label}</div>
      <div className="mt-0.5 break-all text-sm text-foreground">{value ?? "—"}</div>
    </div>
  );
}

export default function DeviceDetail() {
  const { chipId } = useParams();
  const { theme } = useTheme();
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["device", chipId],
    queryFn: () => api.device(chipId!),
    refetchInterval: 15000,
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
        <Link to="/devices" className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
          <ArrowLeft className="h-4 w-4" /> До списку
        </Link>
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
      <Link to="/devices" className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
        <ArrowLeft className="h-4 w-4" /> До списку
      </Link>

      <div className="flex flex-wrap items-center gap-2 sm:gap-3">
        <h1 className="break-all font-mono text-xl font-bold sm:text-2xl">{d.chip_id}</h1>
        <Badge variant={d.is_online ? "online" : "offline"}>{d.is_online ? "онлайн" : "офлайн"}</Badge>
        {d.is_jaam ? (
          <span className="inline-flex items-center gap-1 rounded-full border border-primary/30 bg-primary/10 px-2.5 py-0.5 text-xs font-medium text-primary">
            Офіційна JAAM{d.is_prototype ? " · прототип" : ""}
          </span>
        ) : (
          <span className="rounded-full border border-border/[0.1] bg-muted px-2.5 py-0.5 text-xs text-muted-foreground">
            Самозбірка
          </span>
        )}
        {d.firmware_id && <span className="text-sm text-muted-foreground">ID: {d.firmware_id}</span>}
      </div>

      {d.is_jaam && (
        <Card>
          <CardHeader><CardTitle>Дані реєстру JAAM</CardTitle></CardHeader>
          <CardBody className="grid grid-cols-2 gap-4 sm:grid-cols-4">
            <Field label="HW версія" value={d.hw_version} />
            <Field label="Прототип" value={d.is_prototype ? "так" : "ні"} />
            <Field label="Замовлення" value={d.order_number} />
            <Field label="Клієнт" value={d.customer_info} />
          </CardBody>
        </Card>
      )}

      <div className="grid gap-4 sm:gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader><CardTitle>Інформація</CardTitle></CardHeader>
          <CardBody className="grid grid-cols-2 gap-4 sm:grid-cols-3">
            <Field label="Прошивка" value={
              <span className="font-mono">
                {d.firmware ?? "—"}
                {d.firmware_id && <span className="ml-1 text-muted-foreground">({d.firmware_id})</span>}
              </span>
            } />
            <Field label="Тип HW" value={d.hw_type} />
            <Field label="Сервер" value={d.last_server} />
            <Field label="IP" value={<span className="font-mono">{d.last_ip}</span>} />
            <Field label="Місто" value={d.city} />
            <Field label="Регіон" value={d.region} />
            <Field label="Країна" value={d.country} />
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
              <div className="h-[220px] sm:h-[260px]">
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
          <CardHeader><CardTitle>Сесії ({data.sessions.length})</CardTitle></CardHeader>
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
                <Badge variant={s.ended_at ? "offline" : "online"} className="ml-2 shrink-0">{fmtDuration(s.duration_sec)}</Badge>
              </div>
            ))}
          </CardBody>
        </Card>

        <Card>
          <CardHeader><CardTitle>Події ({data.events.length})</CardTitle></CardHeader>
          <CardBody className="space-y-2">
            {data.events.length === 0 && <div className="text-sm text-muted-foreground">Немає подій</div>}
            {data.events.map((e) => (
              <div key={e.id} className="flex items-center justify-between border-b border-border/[0.07] pb-2 text-sm last:border-0">
                <span className="flex-1 min-w-0 truncate text-foreground">{EVENT_LABEL[e.type] ?? e.type}</span>
                <span className="ml-2 shrink-0 text-xs text-muted-foreground" title={fmtDateTime(e.ts)}>{timeAgo(e.ts)}</span>
              </div>
            ))}
          </CardBody>
        </Card>
      </div>
    </div>
  );
}
