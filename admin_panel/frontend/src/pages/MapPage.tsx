import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { MapContainer, TileLayer, ZoomControl, useMap } from "react-leaflet";
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
    const group = (L as any).markerClusterGroup({
      showCoverageOnHover: false,
      maxClusterRadius: 40,
      removeOutsideVisibleBounds: false,
    });
    groupRef.current = group;
    map.addLayer(group);
    return () => {
      map.removeLayer(group);
      groupRef.current = null;
    };
  }, [map]);

  useEffect(() => {
    const group = groupRef.current;
    if (!group) return;
    group.clearLayers();
    points.forEach((p) => {
      const marker = L.marker([p.lat, p.lon], { icon: pinIcon(p.is_online) });
      const jaamRow = p.is_jaam ? `
        <div style="margin-top:6px;padding-top:6px;border-top:1px solid rgba(0,0,0,0.12)">
          <span style="font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.05em;opacity:.6">Реєстр JAAM</span><br/>
          ${p.map_id ? `🏷 <b style="font-family:monospace">${p.map_id}</b>${p.is_prototype ? ` <svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#f59e0b" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="display:inline;vertical-align:text-bottom"><path d="M10 2v7.527a2 2 0 0 1-.211.896L4.72 20.55a1 1 0 0 0 .9 1.45h12.76a1 1 0 0 0 .9-1.45l-5.069-10.127A2 2 0 0 1 14 9.527V2"/><path d="M8.5 2h7"/><path d="M7 16h10"/></svg>` : ""}<br/>` : ""}
          ${p.hw_version ? `🔩 ${p.hw_version}<br/>` : ""}
          ${p.order_number ? `📦 замовл. ${p.order_number}<br/>` : ""}
          ${p.customer_info ? `👤 ${p.customer_info}` : ""}
        </div>` : "";
      marker.bindPopup(
        `<div style="font-size:13px;line-height:1.6;font-family:system-ui;min-width:180px">
          <b style="font-family:monospace">${p.chip_id}</b><br/>
          ${p.is_online ? "🟢 онлайн" : "⚪ офлайн"}<br/>
          📍 ${[p.city, p.region].filter(Boolean).join(", ") || "—"}<br/>
          🔧 ${p.firmware ?? "—"}<br/>
          📡 ${p.org ?? "—"}<br/>
          ⏱ ${fmtDateTime(p.last_seen)}
          ${jaamRow}
        </div>`,
      );
      group.addLayer(marker);
    });
  }, [points]);

  return null;
}

export default function MapPage() {
  const [status, setStatus] = useState("");
  const [type_, setType] = useState("");
  const { theme } = useTheme();
  const { data, isLoading } = useQuery({
    queryKey: ["geo", status, type_],
    queryFn: () => api.geo(status || undefined, type_ || undefined),
    refetchInterval: 20000,
  });

  const points = data ?? [];
  const online = points.filter((p) => p.is_online).length;

  const tileUrl = theme === "dark"
    ? "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
    : "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png";

  return (
    <div className="relative" style={{ height: "calc(100vh - 53px)" }}>
      {/* On desktop (no mobile header), use full vh */}
      <style>{`@media (min-width: 768px) { .map-root { height: 100vh !important; } }`}</style>
      <div className="map-root absolute inset-0">
        {/* Overlay */}
        <div className="absolute left-3 right-3 top-3 z-[500] flex items-center justify-between gap-2 sm:left-4 sm:right-4 sm:top-4">
          <div className="rounded border border-border/[0.1] bg-card/95 px-3 py-2 backdrop-blur-sm shadow-sm">
            <div className="text-xs font-semibold text-foreground sm:text-sm">
              {points.length} мап · <span className="text-success">{online} онлайн</span>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {isLoading && <Spinner className="h-4 w-4" />}
            <Select value={type_} onChange={(e) => setType(e.target.value)} className="bg-card/95 backdrop-blur-sm text-xs sm:text-sm">
              <option value="">Всі типи</option>
              <option value="jaam">JAAM</option>
              <option value="self">Самозбірка</option>
            </Select>
            <Select value={status} onChange={(e) => setStatus(e.target.value)} className="bg-card/95 backdrop-blur-sm text-xs sm:text-sm">
              <option value="">Усі статуси</option>
              <option value="online">Онлайн</option>
              <option value="offline">Офлайн</option>
            </Select>
          </div>
        </div>

        <MapContainer center={[49, 32]} zoom={6} className="h-full w-full" scrollWheelZoom zoomControl={false}>
          <TileLayer url={tileUrl} attribution="© OpenStreetMap contributors" />
          <ZoomControl position="bottomright" />
          <Clusters points={points} />
        </MapContainer>
      </div>
    </div>
  );
}
