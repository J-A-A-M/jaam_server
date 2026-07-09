export interface Device {
  chip_id: string;
  firmware: string | null;
  firmware_id: string | null;
  hw_type: string | null;
  is_online: boolean;
  first_seen: string;
  last_seen: string;
  last_online_at: string | null;
  connect_time: string | null;
  last_ip: string | null;
  city: string | null;
  region: string | null;
  country: string | null;
  org: string | null;
  location: string | null;
  lat: number | null;
  lon: number | null;
  latency: number | null;
  secure_connection: boolean | null;
  last_server: string | null;
  is_jaam: boolean;
  ever_seen: boolean;
  map_id: string | null;
  hw_version: string | null;
  is_prototype: boolean | null;
  order_number: string | null;
  customer_info: string | null;
}

export interface JaamMap {
  chip_id: string;
  map_id: string | null;
  hw_version: string | null;
  is_prototype: boolean;
  order_number: string | null;
  customer_info: string | null;
  created_at: string;
  updated_at: string;
  ever_seen: boolean;
  is_online: boolean;
  last_seen: string | null;
  firmware: string | null;
  firmware_id: string | null;
}

export interface JaamMapList {
  total: number;
  page: number;
  page_size: number;
  items: JaamMap[];
}

export interface JaamMapInput {
  chip_id: string;
  map_id?: string | null;
  hw_version?: string | null;
  is_prototype: boolean;
  order_number?: string | null;
  customer_info?: string | null;
}

export interface DeviceList {
  total: number;
  page: number;
  page_size: number;
  items: Device[];
}

export interface CountItem { label: string; count: number; }
export interface ProviderCount { label: string; total: number; online: number; }
export interface TrendPoint { ts: string; online: number; }

export interface LatencyStats {
  good: number;
  normal: number;
  poor: number;
  unknown: number;
}

export interface Overview {
  online_now: number;
  jaam_online: number;
  self_online: number;
  registry_total: number;
  total_registered: number;
  unique_24h: number;
  new_24h: number;
  median_online: string;
  by_firmware: CountItem[];
  by_hw: CountItem[];
  by_region: CountItem[];
  by_country: CountItem[];
  by_city: CountItem[];
  by_provider: ProviderCount[];
  latency_stats: LatencyStats;
  latency_by_provider: CountItem[];
  duration_histogram: CountItem[];
  online_trend: TrendPoint[];
  new_per_day: DayPoint[];
  active_per_day: DayPoint[];
}

export interface DayPoint { date: string; count: number; }

export interface DeviceSession {
  id: number;
  server_name: string | null;
  connect_time: string | null;
  started_at: string;
  ended_at: string | null;
  duration_sec: number | null;
  firmware: string | null;
  ip: string | null;
  city: string | null;
  region: string | null;
}

export interface DeviceEvent {
  id: number;
  chip_id?: string;
  type: string;
  ts: string;
  details: string | null;
}

export interface EventList {
  total: number;
  page: number;
  page_size: number;
  items: DeviceEvent[];
}

export interface DeviceDetail {
  device: Device;
  sessions: DeviceSession[];
  sessions_total: number;
  events: DeviceEvent[];
  events_total: number;
}

export interface GeoPoint {
  chip_id: string;
  lat: number;
  lon: number;
  is_online: boolean;
  firmware: string | null;
  city: string | null;
  region: string | null;
  org: string | null;
  last_seen: string;
  is_jaam: boolean;
  map_id: string | null;
  hw_version: string | null;
  is_prototype: boolean;
  order_number: string | null;
  customer_info: string | null;
}

export interface ServerStatus {
  name: string;
  ok: boolean;
  online: number;
  checked_at: string;
}

export interface RedisServerConfig {
  id: number;
  name: string;
  host: string;
  port: number;
  db: number;
  has_password: boolean;
  enabled: boolean;
  created_at: string;
  updated_at: string;
}

export interface RedisServerConfigInput {
  name: string;
  host: string;
  port: number;
  db: number;
  password?: string | null;
  enabled: boolean;
}

export interface RedisServerConfigUpdate {
  name?: string;
  host?: string;
  port?: number;
  db?: number;
  password?: string | null;
  enabled?: boolean;
}

export interface PanelUser {
  id: number;
  username: string;
  role: string;
  created_at: string;
}

export interface PanelUserInput {
  username: string;
  password: string;
  role: string;
}

export interface PasskeyCredential {
  id: number;
  name: string;
  created_at: string;
  last_used_at: string | null;
}

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

// Глобальний обробник неавторизованих відповідей (реєструється в AuthContext).
// Викликається на 401 від захищених ендпоінтів — щоб SPA перекинула на логін,
// коли токен протух або був відкликаний (logout/зміна пароля чи ролі).
let onUnauthorized: (() => void) | null = null;
export function setUnauthorizedHandler(fn: (() => void) | null) {
  onUnauthorized = fn;
}

// Ендпоінти входу: тут 401 означає «невірні дані», а не протухлу сесію.
const AUTH_ENTRY_PREFIXES = ["/api/auth/login", "/api/webauthn/auth/"];

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      detail = (await res.json()).detail ?? detail;
    } catch { /* ignore */ }
    if (res.status === 401 && !AUTH_ENTRY_PREFIXES.some((p) => path.startsWith(p))) {
      onUnauthorized?.();
    }
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204 || res.headers.get("Content-Length") === "0") return undefined as T;
  return res.json() as Promise<T>;
}

export const api = {
  login: (username: string, password: string) =>
    req<{ username: string; role: string }>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    }),
  logout: () => req("/api/auth/logout", { method: "POST" }),
  me: () => req<{ username: string; role: string }>("/api/auth/me"),
  overview: () => req<Overview>("/api/overview"),
  devices: (params: Record<string, string | number | undefined>) => {
    const qs = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== "") qs.set(k, String(v));
    });
    return req<DeviceList>(`/api/devices?${qs.toString()}`);
  },
  device: (chipId: string, sessionsPage = 1, eventsPage = 1) =>
    req<DeviceDetail>(`/api/devices/${encodeURIComponent(chipId)}?sessions_page=${sessionsPage}&events_page=${eventsPage}`),
  sameIp: (chipId: string) =>
    req<Device[]>(`/api/devices/${encodeURIComponent(chipId)}/same-ip`),
  geo: (status?: string, type?: string) => {
    const qs = new URLSearchParams();
    if (status) qs.set("status", status);
    if (type) qs.set("type", type);
    const q = qs.toString();
    return req<GeoPoint[]>(`/api/geo${q ? `?${q}` : ""}`);
  },
  servers: () => req<ServerStatus[]>("/api/servers"),
  serverConfigs: () => req<RedisServerConfig[]>("/api/servers/config"),
  createServerConfig: (body: RedisServerConfigInput) =>
    req<RedisServerConfig>("/api/servers/config", { method: "POST", body: JSON.stringify(body) }),
  updateServerConfig: (id: number, body: RedisServerConfigUpdate) =>
    req<RedisServerConfig>(`/api/servers/config/${id}`, { method: "PUT", body: JSON.stringify(body) }),
  deleteServerConfig: (id: number) =>
    req<void>(`/api/servers/config/${id}`, { method: "DELETE" }),
  testServerConfig: (id: number) =>
    req<ServerStatus>(`/api/servers/config/${id}/test`, { method: "POST" }),
  inventory: (params: Record<string, string | number | undefined>) => {
    const qs = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== "") qs.set(k, String(v));
    });
    return req<JaamMapList>(`/api/inventory?${qs.toString()}`);
  },
  createMap: (body: JaamMapInput) =>
    req<JaamMap>("/api/inventory", { method: "POST", body: JSON.stringify(body) }),
  updateMap: (chipId: string, body: JaamMapInput) =>
    req<JaamMap>(`/api/inventory/${encodeURIComponent(chipId)}`, {
      method: "PUT",
      body: JSON.stringify(body),
    }),
  deleteMap: (chipId: string) =>
    req<void>(`/api/inventory/${encodeURIComponent(chipId)}`, { method: "DELETE" }),
  events: (params: { page?: number; pageSize?: number; q?: string; type?: string; period?: string; sort?: string; order?: string } = {}) => {
    const { page = 1, pageSize = 50, q, type, period, sort, order } = params;
    const qs = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
    if (q)      qs.set("q", q);
    if (type)   qs.set("type", type);
    if (period) qs.set("period", period);
    if (sort)   qs.set("sort", sort);
    if (order)  qs.set("order", order);
    return req<EventList>(`/api/events?${qs.toString()}`);
  },
  users: () => req<PanelUser[]>("/api/users"),
  createUser: (body: PanelUserInput) =>
    req<PanelUser>("/api/users", { method: "POST", body: JSON.stringify(body) }),
  updateUser: (username: string, body: { role?: string; password?: string }) =>
    req<PanelUser>(`/api/users/${encodeURIComponent(username)}`, { method: "PUT", body: JSON.stringify(body) }),
  deleteUser: (username: string) =>
    req<void>(`/api/users/${encodeURIComponent(username)}`, { method: "DELETE" }),
  changeOwnPassword: (old_password: string, new_password: string) =>
    req<void>("/api/users/me/password", { method: "POST", body: JSON.stringify({ old_password, new_password }) }),

  webauthn: {
    registerBegin: (name: string) =>
      req<object>("/api/webauthn/register/begin", { method: "POST", body: JSON.stringify({ name }) }),
    registerComplete: (credential: object) =>
      req<{ ok: boolean; id: number; name: string }>("/api/webauthn/register/complete", {
        method: "POST",
        body: JSON.stringify(credential),
      }),
    authBegin: () =>
      req<{ session_id: string; options: object }>("/api/webauthn/auth/begin", { method: "POST" }),
    authComplete: (session_id: string, credential: object) =>
      req<{ username: string; role: string }>("/api/webauthn/auth/complete", {
        method: "POST",
        body: JSON.stringify({ session_id, credential }),
      }),
    credentials: () => req<PasskeyCredential[]>("/api/webauthn/credentials"),
    deleteCredential: (id: number) =>
      req<void>(`/api/webauthn/credentials/${id}`, { method: "DELETE" }),
  },
};
