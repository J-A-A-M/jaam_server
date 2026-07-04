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
      {/* Sidebar */}
      <aside className="flex w-[210px] shrink-0 flex-col border-r border-white/[0.06] bg-[#08090E]">
        {/* Logo */}
        <div className="px-5 py-5">
          <div className="flex items-center gap-2.5">
            <div className="flex h-7 w-7 items-center justify-center rounded text-primary">
              <Radar className="h-5 w-5" />
            </div>
            <div>
              <div className="text-[15px] font-extrabold leading-none tracking-tight text-foreground">
                JAAM
              </div>
              <div className="mt-0.5 font-mono text-[9px] font-medium uppercase tracking-[0.2em] text-muted-foreground">
                Admin
              </div>
            </div>
          </div>
        </div>

        {/* Divider */}
        <div className="mx-5 h-px bg-white/[0.06]" />

        {/* Nav */}
        <nav className="flex-1 space-y-0.5 px-3 pt-3">
          {nav
            .filter((item) => !item.adminOnly || user?.role === "admin")
            .map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                className={({ isActive }) =>
                  cn(
                    "flex items-center gap-3 border-l-2 px-3 py-2 text-[13px] font-medium transition-all duration-150 rounded-r",
                    isActive
                      ? "border-primary bg-primary/[0.07] text-primary"
                      : "border-transparent text-muted-foreground hover:border-white/[0.1] hover:bg-white/[0.03] hover:text-foreground",
                  )
                }
              >
                <item.icon className="h-[15px] w-[15px] shrink-0" />
                {item.label}
              </NavLink>
            ))}
        </nav>

        {/* Footer */}
        <div className="border-t border-white/[0.06] p-3">
          <div className="mb-1 px-3 font-mono text-[10px] uppercase tracking-[0.1em] text-muted-foreground/70">
            {user?.username}
          </div>
          <button
            onClick={async () => {
              await logout();
              navigate("/login");
            }}
            className="flex w-full items-center gap-3 border-l-2 border-transparent rounded-r px-3 py-2 text-[13px] text-muted-foreground transition-all duration-150 hover:border-danger/40 hover:bg-danger/[0.05] hover:text-danger"
          >
            <LogOut className="h-[15px] w-[15px] shrink-0" />
            Вийти
          </button>
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-x-hidden">
        <Outlet />
      </main>
    </div>
  );
}
