import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { LayoutDashboard, MapPin, Cpu, Server, LogOut, Radar, ClipboardList, Users, Activity, Sun, Moon, Menu, X } from "lucide-react";
import { useAuth } from "./AuthContext";
import { useTheme } from "./ThemeContext";
import { cn } from "@/lib/utils";

const nav = [
  { to: "/", label: "Дашборд", icon: LayoutDashboard, end: true },
  { to: "/devices", label: "Мапи", icon: Cpu },
  { to: "/inventory", label: "Реєстр JAAM", icon: ClipboardList },
  { to: "/map", label: "Карта", icon: MapPin },
  { to: "/servers", label: "Сервери", icon: Server },
  { to: "/events", label: "Події", icon: Activity },
  { to: "/users", label: "Користувачі", icon: Users, adminOnly: true },
];

export default function Layout() {
  const { user, logout } = useAuth();
  const { theme, toggle } = useTheme();
  const navigate = useNavigate();
  const location = useLocation();
  const [open, setOpen] = useState(false);

  // Close drawer on navigation
  useEffect(() => { setOpen(false); }, [location.pathname]);

  // Prevent body scroll when drawer is open
  useEffect(() => {
    document.body.style.overflow = open ? "hidden" : "";
    return () => { document.body.style.overflow = ""; };
  }, [open]);

  const sidebarContent = (
    <>
      {/* Logo */}
      <div className="flex items-center justify-between px-5 py-5">
        <div className="flex items-center gap-2.5">
          <div className="flex h-7 w-7 items-center justify-center rounded text-primary">
            <Radar className="h-5 w-5" />
          </div>
          <div>
            <div className="text-[15px] font-extrabold leading-none tracking-tight text-foreground">JAAM</div>
            <div className="mt-0.5 font-mono text-[9px] font-medium uppercase tracking-[0.2em] text-muted-foreground">Admin</div>
          </div>
        </div>
        {/* Close button — mobile only */}
        <button onClick={() => setOpen(false)} className="text-muted-foreground hover:text-foreground md:hidden">
          <X className="h-5 w-5" />
        </button>
      </div>

      <div className="mx-5 h-px bg-border/[0.07]" />

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
                  "flex items-center gap-3 border-l-2 px-3 py-2.5 text-[13px] font-medium transition-all duration-150 rounded-r",
                  isActive
                    ? "border-primary bg-primary/[0.07] text-primary"
                    : "border-transparent text-muted-foreground hover:border-border/[0.15] hover:bg-border/[0.04] hover:text-foreground",
                )
              }
            >
              <item.icon className="h-[15px] w-[15px] shrink-0" />
              {item.label}
            </NavLink>
          ))}
      </nav>

      {/* Footer */}
      <div className="border-t border-border/[0.07] p-3">
        <div className="mb-1 px-3 font-mono text-[10px] uppercase tracking-[0.1em] text-muted-foreground/70">
          {user?.username}
        </div>
        <button
          onClick={toggle}
          className="flex w-full items-center gap-3 border-l-2 border-transparent rounded-r px-3 py-2 text-[13px] text-muted-foreground transition-all duration-150 hover:border-border/[0.15] hover:bg-border/[0.04] hover:text-foreground"
        >
          {theme === "dark" ? <Sun className="h-[15px] w-[15px] shrink-0" /> : <Moon className="h-[15px] w-[15px] shrink-0" />}
          {theme === "dark" ? "Світла тема" : "Темна тема"}
        </button>
        <button
          onClick={async () => { await logout(); navigate("/login"); }}
          className="flex w-full items-center gap-3 border-l-2 border-transparent rounded-r px-3 py-2 text-[13px] text-muted-foreground transition-all duration-150 hover:border-danger/40 hover:bg-danger/[0.05] hover:text-danger"
        >
          <LogOut className="h-[15px] w-[15px] shrink-0" />
          Вийти
        </button>
      </div>
    </>
  );

  return (
    <div className="flex min-h-screen">
      {/* Mobile backdrop */}
      <div
        className={cn(
          "fixed inset-0 z-40 bg-black/50 backdrop-blur-sm transition-opacity duration-200 md:hidden",
          open ? "opacity-100 pointer-events-auto" : "opacity-0 pointer-events-none",
        )}
        onClick={() => setOpen(false)}
      />

      {/* Sidebar — drawer on mobile, static on desktop */}
      <aside
        className={cn(
          "fixed inset-y-0 left-0 z-50 flex w-[210px] shrink-0 flex-col border-r border-border/[0.07] bg-sidebar",
          "transition-transform duration-200 ease-in-out",
          "md:sticky md:top-0 md:bottom-auto md:h-screen md:self-start md:translate-x-0 md:transition-none",
          open ? "translate-x-0" : "-translate-x-full",
        )}
      >
        {sidebarContent}
      </aside>

      {/* Content column */}
      <div className="flex min-w-0 flex-1 flex-col">
        {/* Mobile top bar */}
        <header className="flex items-center justify-between border-b border-border/[0.07] bg-sidebar px-4 py-3 md:hidden">
          <button
            onClick={() => setOpen(true)}
            className="rounded p-1 text-muted-foreground transition hover:text-foreground"
            aria-label="Меню"
          >
            <Menu className="h-5 w-5" />
          </button>
          <div className="flex items-center gap-2">
            <Radar className="h-4 w-4 text-primary" />
            <span className="text-sm font-extrabold tracking-tight text-foreground">JAAM</span>
          </div>
          <button
            onClick={toggle}
            className="rounded p-1 text-muted-foreground transition hover:text-foreground"
            aria-label="Тема"
          >
            {theme === "dark" ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
          </button>
        </header>

        <main className="flex-1 overflow-x-hidden">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
