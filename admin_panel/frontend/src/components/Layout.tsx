import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { LayoutDashboard, MapPin, Cpu, Server, LogOut, Radar, ClipboardList, Users } from "lucide-react";
import { useAuth } from "./AuthContext";
import { cn } from "@/lib/utils";

const nav = [
  { to: "/", label: "Дашборд", icon: LayoutDashboard, end: true },
  { to: "/devices", label: "Мапи", icon: Cpu },
  { to: "/inventory", label: "Реєстр JAAM", icon: ClipboardList },
  { to: "/map", label: "Карта", icon: MapPin },
  { to: "/servers", label: "Сервери", icon: Server },
  { to: "/users", label: "Користувачі", icon: Users, adminOnly: true },
];

export default function Layout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  return (
    <div className="flex min-h-screen">
      <aside className="flex w-60 shrink-0 flex-col border-r border-border bg-card/60">
        <div className="flex items-center gap-2 px-5 py-5">
          <Radar className="h-6 w-6 text-primary" />
          <span className="text-lg font-bold tracking-tight">JAAM Admin</span>
        </div>
        <nav className="flex-1 space-y-1 px-3">
          {nav
            .filter((item) => !item.adminOnly || user?.role === "admin")
            .map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition",
                  isActive
                    ? "bg-primary/15 text-primary"
                    : "text-muted-foreground hover:bg-muted hover:text-foreground",
                )
              }
            >
              <item.icon className="h-4 w-4" />
              {item.label}
            </NavLink>
          ))}
        </nav>
        <div className="border-t border-border p-3">
          <div className="px-2 pb-2 text-xs text-muted-foreground">{user?.username}</div>
          <button
            onClick={async () => {
              await logout();
              navigate("/login");
            }}
            className="flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm text-muted-foreground transition hover:bg-muted hover:text-foreground"
          >
            <LogOut className="h-4 w-4" />
            Вийти
          </button>
        </div>
      </aside>
      <main className="flex-1 overflow-x-hidden">
        <Outlet />
      </main>
    </div>
  );
}
