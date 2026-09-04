export const API_KEY_STORE = "research_agent_api_key";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export function readApiKey(): string {
  try {
    return localStorage.getItem(API_KEY_STORE) ?? "";
  } catch {
    // private windows and blocked site data both throw here
    return "";
  }
}

/**
 * One place that turns a status code into something a person can act on, so no
 * component has to invent its own wording. The server's own detail wins when
 * it sends one — it knows more than we do.
 */
function explain(status: number, detail?: unknown): string {
  if (typeof detail === "string" && detail) return detail;

  switch (status) {
    case 401:
    case 403:
      return "That API key was rejected. Add a valid key in Settings.";
    case 404:
      return "Not found.";
    case 422:
      return "The server rejected those values. Check the topic length and try again.";
    case 429:
      return "Rate limit reached. Wait for the window to reset, then try again.";
    case 503:
      return "The service is starting up or a dependency is down. Try again shortly.";
    default:
      return `The server returned ${status}.`;
  }
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const key = readApiKey();

  let res: Response;
  try {
    res = await fetch(`/api${path}`, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        ...(key ? { "X-API-Key": key } : {}),
        ...init.headers,
      },
    });
  } catch {
    // fetch only rejects when the request never completed
    throw new ApiError(0, "Could not reach the server. Is the API running?");
  }

  if (!res.ok) {
    const body = (await res.json().catch(() => ({}))) as { detail?: unknown };
    throw new ApiError(res.status, explain(res.status, body.detail));
  }

  return res.json() as Promise<T>;
}

/** The PDF route returns bytes, not JSON, so it can't go through api(). */
export function pdfUrl(jobId: string): string {
  return `/api/result/${jobId}/pdf`;
}
