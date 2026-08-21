import { Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "./components/AuthContext";
import { Spinner } from "./components/ui";
import Layout from "./components/Layout";
import Login from "./pages/Login";
import Dashboard from "./pages/Dashboard";
import Devices from "./pages/Devices";
import DeviceDetail from "./pages/DeviceDetail";
import Inventory from "./pages/Inventory";
import MapPage from "./pages/MapPage";
import Servers from "./pages/Servers";
import Events from "./pages/Events";
import Users from "./pages/Users";
import Settings from "./pages/Settings";
import Account from "./pages/Account";
import type { ReactNode } from "react";

function Protected({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();
  if (loading)
    return (
      <div className="flex min-h-screen items-center justify-center">
        <Spinner className="h-8 w-8" />
      </div>
    );
  if (!user) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route
        element={
          <Protected>
            <Layout />
          </Protected>
        }
      >
        <Route path="/" element={<Dashboard />} />
        <Route path="/devices" element={<Devices />} />
        <Route path="/devices/:chipId" element={<DeviceDetail />} />
        <Route path="/inventory" element={<Inventory />} />
        <Route path="/map" element={<MapPage />} />
        <Route path="/servers" element={<Servers />} />
        <Route path="/events" element={<Events />} />
        <Route path="/users" element={<Users />} />
        <Route path="/settings" element={<Settings />} />
        <Route path="/account" element={<Account />} />
      </Route>
    </Routes>
  );
}
