import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { MapContainer, TileLayer, useMap } from "react-leaflet";
import L from "leaflet";
import "leaflet.markercluster";
import "leaflet.markercluster/dist/MarkerCluster.css";
import "leaflet.markercluster/dist/MarkerCluster.Default.css";
import { api, type GeoPoint } from "@/lib/api";
import { Select, Spinner } from "@/components/ui";
import { fmtDateTime } from "@/lib/utils";

function pinIcon(online: boolean) {
  const color = online ? "#22c55e" : "#64748b";
  return L.divIcon({
    className: "",
    html: `<div style="width:16px;height:16px;border-radius:50% 50% 50% 0;transform:rotate(-45deg);background:${color};border:2px solid #0b111e;box-shadow:0 0 4px rgba(0,0,0,.5)"></div>`,
    iconSize: [16, 16],
    iconAnchor: [8, 16],
    popupAnchor: [0, -16],
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
        `<div style="font-size:13px;line-height:1.5">
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
  const { data, isLoading } = useQuery({
    queryKey: ["geo", status],
    queryFn: () => api.geo(status || undefined),
    refetchInterval: 20000,
  });

  const points = data ?? [];
  const online = points.filter((p) => p.is_online).length;

  return (
    <div className="relative h-screen">
      <div className="absolute left-4 right-4 top-4 z-[500] flex items-center justify-between">
        <div className="rounded-lg border border-border bg-card/90 px-4 py-2 backdrop-blur">
          <div className="text-sm font-semibold">
            {points.length} мап на карті · <span className="text-success">{online} онлайн</span>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {isLoading && <Spinner className="h-4 w-4" />}
          <Select value={status} onChange={(e) => setStatus(e.target.value)} className="bg-card/90 backdrop-blur">
            <option value="">Усі</option>
            <option value="online">Тільки онлайн</option>
            <option value="offline">Тільки офлайн</option>
          </Select>
        </div>
      </div>
      <MapContainer center={[49, 32]} zoom={6} className="h-full w-full" scrollWheelZoom>
        <TileLayer url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" attribution="© OpenStreetMap" />
        <Clusters points={points} />
      </MapContainer>
    </div>
  );
}
