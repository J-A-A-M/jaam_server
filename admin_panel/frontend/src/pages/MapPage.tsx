import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { MapContainer, TileLayer, useMap } from "react-leaflet";
import L from "leaflet";
import "leaflet.markercluster";
import "leaflet.markercluster/dist/MarkerCluster.css";
import "leaflet.markercluster/dist/MarkerCluster.Default.css";
import { api, type GeoPoint } from "@/lib/api";
import { Select, Spinner } from "@/components/ui";
import { useTheme } from "@/components/ThemeContext";
import { fmtDateTime } from "@/lib/utils";

function pinIcon(online: boolean) {
  const color = online ? "#22c55e" : "#64748b";
  return L.divIcon({
    className: "",
    html: `<div style="width:14px;height:14px;border-radius:50%;background:${color};border:2px solid rgba(0,0,0,0.4);box-shadow:0 0 4px rgba(0,0,0,.3)"></div>`,
    iconSize: [14, 14],
    iconAnchor: [7, 7],
    popupAnchor: [0, -10],
  });
}

function Clusters({ points }: { points: GeoPoint[] }) {
  const map = useMap();
  const groupRef = useRef<L.MarkerClusterGroup | null>(null);

  useEffect(() => {
    if (!groupRef.current) {
      groupRef.current = (L as any).markerClusterGroup({
        showCoverageOnHover: false,
        maxClusterRadius: 40,
      });
      map.addLayer(groupRef.current);
    }
    const group = groupRef.current!;
    group.clearLayers();
    points.forEach((p) => {
      const marker = L.marker([p.lat, p.lon], { icon: pinIcon(p.is_online) });
      marker.bindPopup(
        `<div style="font-size:13px;line-height:1.6;font-family:system-ui">
          <b style="font-family:monospace">${p.chip_id}</b><br/>
          ${p.is_online ? "🟢 онлайн" : "⚪ офлайн"}<br/>
          📍 ${[p.city, p.region].filter(Boolean).join(", ") || "—"}<br/>
          🔧 ${p.firmware ?? "—"}<br/>
          📡 ${p.org ?? "—"}<br/>
          ⏱ ${fmtDateTime(p.last_seen)}
        </div>`,
      );
      group.addLayer(marker);
    });
  }, [points, map]);

  return null;
}

export default function MapPage() {
  const [status, setStatus] = useState("");
  const { theme } = useTheme();
  const { data, isLoading } = useQuery({
    queryKey: ["geo", status],
    queryFn: () => api.geo(status || undefined),
    refetchInterval: 20000,
  });

  const points = data ?? [];
  const online = points.filter((p) => p.is_online).length;

  const tileUrl = theme === "dark"
    ? "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
    : "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png";

  return (
    <div className="relative h-screen">
      <div className="absolute left-4 right-4 top-4 z-[500] flex items-center justify-between">
        <div className="rounded border border-border/[0.1] bg-card/95 px-4 py-2 backdrop-blur-sm shadow-sm">
          <div className="text-sm font-semibold text-foreground">
            {points.length} мап на карті · <span className="text-success">{online} онлайн</span>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {isLoading && <Spinner className="h-4 w-4" />}
          <Select value={status} onChange={(e) => setStatus(e.target.value)} className="bg-card/95 backdrop-blur-sm">
            <option value="">Усі</option>
            <option value="online">Тільки онлайн</option>
            <option value="offline">Тільки офлайн</option>
          </Select>
        </div>
      </div>
      <MapContainer center={[49, 32]} zoom={6} className="h-full w-full" scrollWheelZoom>
        <TileLayer url={tileUrl} attribution="© OpenStreetMap contributors" />
        <Clusters points={points} />
      </MapContainer>
    </div>
  );
}
