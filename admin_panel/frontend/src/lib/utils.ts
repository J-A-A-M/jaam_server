import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function timeAgo(iso: string | null | undefined): string {
  if (!iso) return "—";
  const then = new Date(iso).getTime();
  const diff = Math.max(0, Date.now() - then) / 1000;
  if (diff < 60) return `${Math.floor(diff)} с тому`;
  if (diff < 3600) return `${Math.floor(diff / 60)} хв тому`;
  if (diff < 86400) return `${Math.floor(diff / 3600)} год тому`;
  return `${Math.floor(diff / 86400)} дн тому`;
}

export function fmtDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("uk-UA");
}

export function fmtDuration(sec: number | null | undefined): string {
  if (sec == null) return "—";
  const h = Math.floor(sec / 3600);
  const m = Math.floor((sec % 3600) / 60);
  if (h === 0) return `${m}хв`;
  if (m === 0) return `${h}г`;
  return `${h}г ${m}хв`;
}
