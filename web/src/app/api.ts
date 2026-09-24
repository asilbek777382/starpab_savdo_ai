/** Backend API klienti: sessiya httpOnly cookie'da, shuning uchun credentials: "include". */

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

const SHOP_KEY = "nv_shop";

export function getShopId(): string | null {
  try {
    return localStorage.getItem(SHOP_KEY);
  } catch {
    return null;
  }
}

export function setShopId(id: number | null) {
  try {
    if (id === null) localStorage.removeItem(SHOP_KEY);
    else localStorage.setItem(SHOP_KEY, String(id));
  } catch {
    /* e'tiborsiz */
  }
}

function detailMessage(body: unknown, status: number): string {
  if (body && typeof body === "object" && "detail" in body) {
    const d = (body as { detail: unknown }).detail;
    if (typeof d === "string") return d;
    if (Array.isArray(d) && d[0]?.msg) return String(d[0].msg);
  }
  return `HTTP ${status}`;
}

export async function api<T>(path: string, init: RequestInit & { json?: unknown } = {}): Promise<T> {
  const headers = new Headers(init.headers);
  const shopId = getShopId();
  if (shopId) headers.set("X-Shop-Id", shopId);
  let body = init.body;
  if (init.json !== undefined) {
    headers.set("Content-Type", "application/json");
    body = JSON.stringify(init.json);
  }
  const resp = await fetch(path, { ...init, headers, body, credentials: "include" });
  if (resp.status === 204) return undefined as T;
  const data = resp.headers.get("content-type")?.includes("json") ? await resp.json() : null;
  if (!resp.ok) throw new ApiError(resp.status, detailMessage(data, resp.status));
  return data as T;
}

export const get = <T>(path: string) => api<T>(path);
export const post = <T>(path: string, json?: unknown) => api<T>(path, { method: "POST", json });
export const put = <T>(path: string, json?: unknown) => api<T>(path, { method: "PUT", json });
export const patch = <T>(path: string, json?: unknown) => api<T>(path, { method: "PATCH", json });
export const del = <T>(path: string) => api<T>(path, { method: "DELETE" });
