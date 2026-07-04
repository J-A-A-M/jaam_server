import { useQuery } from "@tanstack/react-query";
import { Server, CheckCircle2, XCircle } from "lucide-react";
import { api } from "@/lib/api";
import { Card, CardBody, Spinner } from "@/components/ui";
import { fmtDateTime } from "@/lib/utils";

export default function Servers() {
  const { data, isLoading } = useQuery({
    queryKey: ["servers"],
    queryFn: api.servers,
    refetchInterval: 10000,
  });

  return (
    <div className="space-y-4 p-6">
      <div>
        <h1 className="text-2xl font-bold">Сервери</h1>
        <p className="text-sm text-muted-foreground">Стан Redis-інстансів та кількість клієнтів</p>
      </div>

      {isLoading || !data ? (
        <div className="flex justify-center py-20">
          <Spinner className="h-8 w-8" />
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {data.map((s) => (
            <Card key={s.name}>
              <CardBody className="pt-5">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Server className="h-5 w-5 text-muted-foreground" />
                    <span className="font-mono text-sm text-foreground">{s.name}</span>
                  </div>
                  {s.ok ? (
                    <CheckCircle2 className="h-5 w-5 text-success" />
                  ) : (
                    <XCircle className="h-5 w-5 text-danger" />
                  )}
                </div>
                <div className="mt-4 font-mono text-3xl font-bold text-primary">{s.ok ? s.online : "—"}</div>
                <div className="text-xs text-muted-foreground">мап онлайн</div>
                <div className="mt-3 text-xs text-muted-foreground">
                  {s.ok ? (
                    <span className="text-success">доступний</span>
                  ) : (
                    <span className="text-danger">недоступний</span>
                  )} · перевірено {fmtDateTime(s.checked_at)}
                </div>
              </CardBody>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
