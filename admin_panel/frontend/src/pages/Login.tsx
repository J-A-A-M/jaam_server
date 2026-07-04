import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Radar } from "lucide-react";
import { useAuth } from "@/components/AuthContext";
import { Button, Card, CardBody, Input, Spinner } from "@/components/ui";

export default function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await login(username, password);
      navigate("/");
    } catch {
      setError("Невірний логін або пароль");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4">
      <Card className="w-full max-w-sm">
        <CardBody className="pt-8">
          <div className="mb-6 flex flex-col items-center gap-2">
            <Radar className="h-10 w-10 text-primary" />
            <h1 className="text-xl font-bold">JAAM Адмін-панель</h1>
            <p className="text-sm text-muted-foreground">Моніторинг мап</p>
          </div>
          <form onSubmit={submit} className="space-y-3">
            <Input
              placeholder="Логін"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              autoFocus
            />
            <Input
              type="password"
              placeholder="Пароль"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
            {error && <div className="text-sm text-danger">{error}</div>}
            <Button type="submit" className="w-full" disabled={loading}>
              {loading ? <Spinner /> : "Увійти"}
            </Button>
          </form>
        </CardBody>
      </Card>
    </div>
  );
}
