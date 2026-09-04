import { beforeEach, describe, expect, it, vi } from "vitest";
import { api, ApiError, API_KEY_STORE, readApiKey } from "../api/client";

function mockFetch(response: Partial<Response> & { json?: () => Promise<unknown> }) {
  return vi.spyOn(globalThis, "fetch").mockResolvedValue({
    ok: true,
    status: 200,
    json: async () => ({}),
    ...response,
  } as Response);
}

describe("api client", () => {
  beforeEach(() => localStorage.clear());

  it("prefixes every path with /api", async () => {
    const fetchSpy = mockFetch({ json: async () => ({ ok: true }) });
    await api("/stats");
    expect(fetchSpy).toHaveBeenCalledWith("/api/stats", expect.anything());
  });

  it("sends the saved key as X-API-Key", async () => {
    localStorage.setItem(API_KEY_STORE, "secret-key");
    const fetchSpy = mockFetch({ json: async () => ({}) });

    await api("/stats");

    const headers = fetchSpy.mock.calls[0]?.[1]?.headers as Record<string, string>;
    expect(headers["X-API-Key"]).toBe("secret-key");
  });

  it("omits the header entirely when no key is saved", async () => {
    const fetchSpy = mockFetch({ json: async () => ({}) });
    await api("/stats");

    const headers = fetchSpy.mock.calls[0]?.[1]?.headers as Record<string, string>;
    expect(headers).not.toHaveProperty("X-API-Key");
  });

  it("turns a 401 into advice, not a status code", async () => {
    mockFetch({ ok: false, status: 401, json: async () => ({}) });
    await expect(api("/stats")).rejects.toThrow(/API key was rejected/);
  });

  it("prefers the server's own detail message", async () => {
    mockFetch({ ok: false, status: 400, json: async () => ({ detail: "Input blocked by safety guardrail." }) });
    await expect(api("/research")).rejects.toThrow("Input blocked by safety guardrail.");
  });

  it("explains a rate limit", async () => {
    mockFetch({ ok: false, status: 429, json: async () => ({}) });
    await expect(api("/research")).rejects.toThrow(/Rate limit reached/);
  });

  it("reports an unreachable server rather than a raw network error", async () => {
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new TypeError("Failed to fetch"));
    await expect(api("/stats")).rejects.toThrow(/Could not reach the server/);
  });

  it("carries the status code on the error", async () => {
    mockFetch({ ok: false, status: 404, json: async () => ({}) });
    await expect(api("/reports/nope")).rejects.toMatchObject({ status: 404 });
  });

  it("readApiKey returns an empty string when storage throws", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    expect(readApiKey()).toBe("");
  });

  it("ApiError keeps its name for instanceof checks", () => {
    const error = new ApiError(500, "boom");
    expect(error).toBeInstanceOf(Error);
    expect(error.name).toBe("ApiError");
  });
});
