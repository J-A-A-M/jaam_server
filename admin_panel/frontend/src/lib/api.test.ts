import { beforeEach, describe, expect, it, vi } from "vitest";
import { api, ApiError, setUnauthorizedHandler } from "./api";

function fakeResponse(opts: {
  ok: boolean;
  status?: number;
  body?: unknown;
  contentLength?: string | null;
}): Response {
  const { ok, status = 200, body, contentLength = null } = opts;
  return {
    ok,
    status,
    statusText: "",
    headers: { get: (h: string) => (h === "Content-Length" ? contentLength : null) },
    json: async () => body,
  } as unknown as Response;
}

describe("api req()", () => {
  beforeEach(() => {
    setUnauthorizedHandler(null);
    vi.restoreAllMocks();
  });

  it("returns parsed JSON on success", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(fakeResponse({ ok: true, body: { username: "a", role: "admin" } })));
    await expect(api.me()).resolves.toEqual({ username: "a", role: "admin" });
  });

  it("returns undefined on 204", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(fakeResponse({ ok: true, status: 204 })));
    await expect(api.logout()).resolves.toBeUndefined();
  });

  it("throws ApiError with status and detail on error", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(fakeResponse({ ok: false, status: 500, body: { detail: "boom" } })));
    await expect(api.overview()).rejects.toMatchObject({ status: 500, message: "boom" });
    await expect(api.overview()).rejects.toBeInstanceOf(ApiError);
  });

  it("calls the unauthorized handler on 401 from a protected endpoint", async () => {
    const onUnauth = vi.fn();
    setUnauthorizedHandler(onUnauth);
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(fakeResponse({ ok: false, status: 401, body: { detail: "nope" } })));
    await expect(api.overview()).rejects.toBeInstanceOf(ApiError);
    expect(onUnauth).toHaveBeenCalledTimes(1);
  });

  it("does NOT call the handler on 401 from the login endpoint", async () => {
    const onUnauth = vi.fn();
    setUnauthorizedHandler(onUnauth);
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(fakeResponse({ ok: false, status: 401, body: { detail: "bad creds" } })));
    await expect(api.login("u", "p")).rejects.toBeInstanceOf(ApiError);
    expect(onUnauth).not.toHaveBeenCalled();
  });
});
