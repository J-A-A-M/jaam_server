import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Trash2, ArrowUp, ArrowDown, SlidersHorizontal } from "lucide-react";
import { api, type HardwareVersion } from "@/lib/api";
import { Button, Card, CardBody, Input, Spinner } from "@/components/ui";

function HwVersionsSection() {
  const qc = useQueryClient();
  const [name, setName] = useState("");
  const [error, setError] = useState("");

  const { data: versions, isLoading } = useQuery({
    queryKey: ["hw-versions"],
    queryFn: api.hwVersions,
  });

  const invalidate = () => qc.invalidateQueries({ queryKey: ["hw-versions"] });

  const createMut = useMutation({
    mutationFn: (n: string) => api.createHwVersion(n),
    onSuccess: () => { setName(""); setError(""); invalidate(); },
    onError: (e: Error) => setError(e.message),
  });

  const deleteMut = useMutation({
    mutationFn: (id: number) => api.deleteHwVersion(id),
    onSuccess: invalidate,
    onError: (e: Error) => alert(e.message),
  });

  const reorderMut = useMutation({
    mutationFn: (orderedIds: number[]) => api.reorderHwVersions(orderedIds),
    onSuccess: invalidate,
  });

  const move = (idx: number, dir: -1 | 1) => {
    if (!versions) return;
    const target = idx + dir;
    if (target < 0 || target >= versions.length) return;
    const ids = versions.map((v) => v.id);
    [ids[idx], ids[target]] = [ids[target], ids[idx]];
    reorderMut.mutate(ids);
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = name.trim();
    if (!trimmed) { setError("Назва не може бути порожньою"); return; }
    createMut.mutate(trimmed);
  };

  return (
    <>
      <div>
        <h2 className="text-base font-semibold text-foreground">Апаратні версії JAAM</h2>
        <p className="text-sm text-muted-foreground">
          Список значень hw_version, доступних у формі реєстру мап («Реєстр JAAM», модалка мапи)
        </p>
      </div>

      <Card className="overflow-hidden">
        {isLoading ? (
          <div className="py-16 text-center"><Spinner className="mx-auto h-6 w-6" /></div>
        ) : versions?.length === 0 ? (
          <div className="py-10 text-center text-sm text-muted-foreground">Список порожній</div>
        ) : (
          <ul className="divide-y divide-border/[0.07]">
            {versions?.map((v: HardwareVersion, idx: number) => (
              <li key={v.id} className="flex items-center justify-between gap-3 px-4 py-2.5">
                <span className="font-mono text-sm text-foreground">{v.name}</span>
                <div className="flex items-center gap-1">
                  <button
                    onClick={() => move(idx, -1)}
                    disabled={idx === 0 || reorderMut.isPending}
                    className="rounded-md p-1.5 text-muted-foreground transition hover:bg-muted hover:text-foreground disabled:opacity-30"
                    title="Вище"
                  >
                    <ArrowUp className="h-4 w-4" />
                  </button>
                  <button
                    onClick={() => move(idx, 1)}
                    disabled={idx === versions.length - 1 || reorderMut.isPending}
                    className="rounded-md p-1.5 text-muted-foreground transition hover:bg-muted hover:text-foreground disabled:opacity-30"
                    title="Нижче"
                  >
                    <ArrowDown className="h-4 w-4" />
                  </button>
                  <button
                    onClick={() => { if (confirm(`Видалити «${v.name}» зі списку?`)) deleteMut.mutate(v.id); }}
                    disabled={deleteMut.isPending}
                    className="rounded-md p-1.5 text-muted-foreground transition hover:bg-danger/15 hover:text-danger disabled:opacity-40"
                    title="Видалити"
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </Card>

      <form onSubmit={handleSubmit} className="flex items-start gap-2">
        <div className="flex-1">
          <Input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="напр. JAAM3.4"
          />
          {error && <div className="mt-1 text-sm text-danger">{error}</div>}
        </div>
        <Button type="submit" disabled={createMut.isPending}>
          {createMut.isPending ? <Spinner /> : <Plus className="h-4 w-4" />}
          <span className="hidden sm:inline">Додати</span>
        </Button>
      </form>
    </>
  );
}

export default function Settings() {
  return (
    <div className="space-y-6 p-4 sm:p-6">
      <div className="flex items-center gap-2.5">
        <SlidersHorizontal className="h-5 w-5 text-muted-foreground" />
        <div>
          <h1 className="text-xl font-bold sm:text-2xl">Налаштування</h1>
          <p className="text-sm text-muted-foreground">Довідники, що використовуються у формах панелі</p>
        </div>
      </div>

      <HwVersionsSection />
    </div>
  );
}
