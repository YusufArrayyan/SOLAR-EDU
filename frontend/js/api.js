// Klien API. Semua permintaan yang mengubah data membawa header X-Solar-Edu (perlindungan CSRF).
export class ApiError extends Error {
  constructor(status, detail) {
    const pesan = typeof detail === "string" ? detail : detail?.pesan || "Terjadi kesalahan.";
    super(pesan);
    this.status = status;
    this.kolom = typeof detail === "object" && detail ? detail.kolom || {} : {};
  }
}

let onUnauthorized = () => {};
export function setUnauthorizedHandler(fn) { onUnauthorized = fn; }

export async function api(path, { method = "GET", body, signal } = {}) {
  const headers = { Accept: "application/json" };
  if (method !== "GET") headers["X-Solar-Edu"] = "1";
  if (body !== undefined) headers["Content-Type"] = "application/json";
  let res;
  try {
    res = await fetch(path, { method, headers, body: body === undefined ? undefined : JSON.stringify(body), signal, credentials: "same-origin" });
  } catch (e) {
    if (e.name === "AbortError") throw e;
    throw new ApiError(0, "Server tidak dapat dihubungi. Periksa koneksi jaringan kampus, lalu coba lagi.");
  }
  const data = res.headers.get("content-type")?.includes("json") ? await res.json() : null;
  if (!res.ok) {
    if (res.status === 401 && !path.startsWith("/api/auth/masuk")) onUnauthorized(data?.detail);
    throw new ApiError(res.status, data?.detail ?? `Galat ${res.status}.`);
  }
  return data;
}
