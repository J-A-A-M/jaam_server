import { cn } from "@/lib/utils";
import type { HTMLAttributes, InputHTMLAttributes, ButtonHTMLAttributes, ReactNode } from "react";

export function Card({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        "rounded-md border border-white/[0.07] bg-card shadow-[0_1px_0_rgba(255,255,255,0.04)_inset]",
        className,
      )}
      {...props}
    />
  );
}

export function CardHeader({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("px-5 pt-4 pb-3", className)} {...props} />;
}

export function CardTitle({ className, ...props }: HTMLAttributes<HTMLHeadingElement>) {
  return (
    <h3
      className={cn(
        "text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-foreground",
        className,
      )}
      {...props}
    />
  );
}

export function CardBody({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("px-5 pb-5", className)} {...props} />;
}

export function Badge({
  variant = "muted",
  className,
  children,
}: {
  variant?: "online" | "offline" | "muted";
  className?: string;
  children: ReactNode;
}) {
  const styles = {
    online: "bg-success/10 text-success border-success/20",
    offline: "bg-white/[0.03] text-muted-foreground border-white/[0.06]",
    muted: "bg-white/[0.03] text-foreground border-white/[0.06]",
  }[variant];

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium font-mono",
        styles,
        className,
      )}
    >
      {variant === "online" && (
        <span className="relative flex h-1.5 w-1.5">
          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-success opacity-60" />
          <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-success" />
        </span>
      )}
      {variant === "offline" && <span className="h-1.5 w-1.5 rounded-full bg-muted-foreground/50" />}
      {children}
    </span>
  );
}

export function Button({ className, children, ...props }: ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      className={cn(
        "inline-flex items-center justify-center gap-2 rounded bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground transition-all duration-150",
        "hover:brightness-110 hover:shadow-glow-sm active:scale-[0.98] disabled:opacity-40 disabled:cursor-not-allowed",
        className,
      )}
      {...props}
    >
      {children}
    </button>
  );
}

export function Input({ className, ...props }: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      className={cn(
        "w-full rounded border border-white/[0.08] bg-muted/60 px-3 py-2 text-sm font-sans outline-none",
        "placeholder:text-muted-foreground/60 transition-colors",
        "focus:border-primary/60 focus:bg-muted",
        className,
      )}
      {...props}
    />
  );
}

export function Select({ className, ...props }: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      className={cn(
        "rounded border border-white/[0.08] bg-muted/60 px-3 py-2 text-sm outline-none",
        "transition-colors focus:border-primary/60",
        className,
      )}
      {...props}
    />
  );
}

export function Textarea({ className, ...props }: React.TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      className={cn(
        "w-full rounded border border-white/[0.08] bg-muted/60 px-3 py-2 text-sm outline-none",
        "placeholder:text-muted-foreground/60 transition-colors",
        "focus:border-primary/60 focus:bg-muted",
        className,
      )}
      {...props}
    />
  );
}

export function Modal({
  open,
  onClose,
  title,
  children,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
}) {
  if (!open) return null;
  return (
    <div
      className="fixed inset-0 z-[1000] flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="w-full max-w-lg animate-fade-in rounded-md border border-white/[0.1] bg-card shadow-[0_24px_64px_rgba(0,0,0,0.7)]"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-white/[0.07] px-5 py-3">
          <span className="text-sm font-semibold text-foreground">{title}</span>
          <button
            onClick={onClose}
            className="text-muted-foreground transition hover:text-foreground text-lg leading-none"
          >
            ×
          </button>
        </div>
        <div className="p-5">{children}</div>
      </div>
    </div>
  );
}

export function Spinner({ className }: { className?: string }) {
  return (
    <div
      className={cn(
        "h-4 w-4 animate-spin rounded-full border-2 border-white/10 border-t-primary",
        className,
      )}
    />
  );
}

export function Stat({
  label,
  value,
  hint,
  accent,
}: {
  label: string;
  value: ReactNode;
  hint?: ReactNode;
  accent?: boolean;
}) {
  return (
    <Card className={cn("transition-all duration-200", accent && "border-primary/20 shadow-glow-sm")}>
      <CardBody className="pt-5">
        <div className="text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">
          {label}
        </div>
        <div
          className={cn(
            "mt-1.5 font-mono text-[2.1rem] font-bold leading-none",
            accent ? "text-primary" : "text-foreground",
          )}
        >
          {value}
        </div>
        {hint && <div className="mt-1.5 text-xs font-mono text-muted-foreground">{hint}</div>}
      </CardBody>
    </Card>
  );
}
