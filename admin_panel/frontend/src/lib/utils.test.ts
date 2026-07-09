import { afterEach, describe, expect, it, vi } from "vitest";
import { cn, fmtDateTime, fmtDuration, timeAgo } from "./utils";

describe("cn", () => {
  it("joins truthy classes and drops falsy", () => {
    expect(cn("a", false && "b", undefined, "c")).toBe("a c");
  });

  it("merges conflicting tailwind classes (last wins)", () => {
    expect(cn("p-2", "p-4")).toBe("p-4");
  });
});

describe("fmtDuration", () => {
  it("handles null", () => {
    expect(fmtDuration(null)).toBe("—");
    expect(fmtDuration(undefined)).toBe("—");
  });

  it("formats seconds into г/хв", () => {
    expect(fmtDuration(45)).toBe("0хв"); // < 1 хв
    expect(fmtDuration(90)).toBe("1хв");
    expect(fmtDuration(3600)).toBe("1г");
    expect(fmtDuration(5400)).toBe("1г 30хв");
  });
});

describe("fmtDateTime", () => {
  it("returns dash for empty", () => {
    expect(fmtDateTime(null)).toBe("—");
    expect(fmtDateTime(undefined)).toBe("—");
  });

  it("formats a real date to a non-empty string", () => {
    const s = fmtDateTime("2026-01-15T10:00:00Z");
    expect(s).not.toBe("—");
    expect(s.length).toBeGreaterThan(0);
  });
});

describe("timeAgo", () => {
  afterEach(() => vi.useRealTimers());

  it("returns dash for empty", () => {
    expect(timeAgo(null)).toBe("—");
  });

  it("formats relative distances", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-01-15T12:00:00Z"));
    expect(timeAgo("2026-01-15T11:59:30Z")).toBe("30 с тому");
    expect(timeAgo("2026-01-15T11:30:00Z")).toBe("30 хв тому");
    expect(timeAgo("2026-01-15T10:00:00Z")).toBe("2 год тому");
    expect(timeAgo("2026-01-13T12:00:00Z")).toBe("2 дн тому");
  });
});
