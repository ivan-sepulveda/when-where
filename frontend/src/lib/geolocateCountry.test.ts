import { afterEach, describe, expect, it, vi } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { useCountry } from "./geolocateCountry";

describe("useCountry", () => {
  const originalFetch = global.fetch;

  afterEach(() => {
    global.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  it("starts in a loading state with no country yet", () => {
    global.fetch = vi.fn(() => new Promise(() => {})) as unknown as typeof fetch;

    const { result } = renderHook(() => useCountry());

    expect(result.current.loading).toBe(true);
    expect(result.current.country).toBeNull();
    expect(result.current.error).toBeNull();
  });

  it("returns the country on a successful lookup", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ ip: "8.8.8.8", country: "US" }),
    }) as unknown as typeof fetch;

    const { result } = renderHook(() => useCountry());

    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(result.current.country).toBe("US");
    expect(result.current.error).toBeNull();
  });

  it("sets an error when the API responds with a non-ok status", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 429,
      json: async () => ({}),
    }) as unknown as typeof fetch;

    const { result } = renderHook(() => useCountry());

    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(result.current.country).toBeNull();
    expect(result.current.error).toContain("429");
  });

  it("sets an error when fetch itself rejects (e.g. offline)", async () => {
    global.fetch = vi.fn().mockRejectedValue(new Error("network down"));

    const { result } = renderHook(() => useCountry());

    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(result.current.country).toBeNull();
    expect(result.current.error).toBe("network down");
  });

  it("does not update state after unmount (cancelled cleanup)", async () => {
    let resolveFetch: (value: unknown) => void = () => {};
    global.fetch = vi.fn(
      () => new Promise((resolve) => {
        resolveFetch = resolve;
      })
    ) as unknown as typeof fetch;

    const { result, unmount } = renderHook(() => useCountry());
    unmount();

    resolveFetch({
      ok: true,
      json: async () => ({ ip: "8.8.8.8", country: "US" }),
    });

    // Give the resolved promise a tick to (not) apply state updates.
    await new Promise((r) => setTimeout(r, 0));

    expect(result.current.loading).toBe(true);
    expect(result.current.country).toBeNull();
  });
});
