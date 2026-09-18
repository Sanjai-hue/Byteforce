/** Typed client for the ReqGuard backend. */

import type {
  AmbiguityFinding,
  AnalysisStatus,
  ApiErrorBody,
  CleanRequirementSet,
  DependencyGraph,
  DocumentSummary,
  Issue,
  MissingInfoFinding,
  PairFinding,
  Requirement,
  TraceabilityRow,
  UploadResponse,
} from "@/types/api";

const BASE_URL = (import.meta.env.VITE_API_URL ?? "http://localhost:8000").replace(/\/$/, "");

export class ApiError extends Error {
  readonly code: string;
  readonly status: number;

  constructor(message: string, code: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${BASE_URL}${path}`, {
      headers: init?.body instanceof FormData ? undefined : { "Content-Type": "application/json" },
      ...init,
    });
  } catch {
    throw new ApiError(
      "Could not reach the ReqGuard server. Check that the backend is running.",
      "network_error",
      0,
    );
  }

  if (!response.ok) {
    let code = "http_error";
    let message = `Request failed (${response.status}).`;
    try {
      const body = (await response.json()) as ApiErrorBody;
      if (body?.error) {
        code = body.error.code;
        message = body.error.message;
      }
    } catch {
      /* non-JSON error body: keep the generic message */
    }
    throw new ApiError(message, code, response.status);
  }

  if (response.status === 204) return undefined as T;
  const contentType = response.headers.get("content-type") ?? "";
  if (!contentType.includes("application/json")) {
    return (await response.text()) as unknown as T;
  }
  return (await response.json()) as T;
}

export const api = {
  baseUrl: BASE_URL,

  health: () => request<{ status: string }>("/health"),

  systemStatus: () =>
    request<{
      database: { configured: boolean; reachable: boolean };
      embeddings: { model: string; dimensions: number; ready: boolean; error: string | null };
      llm: { provider: string; model: string; configured: boolean };
    }>("/api/system/status"),

  uploadDocument: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<UploadResponse>("/api/documents/upload", { method: "POST", body: form });
  },

  startAnalysis: (documentId: string) =>
    request<{ document_id: string; status: string; message: string }>(
      `/api/documents/${documentId}/analyze`,
      { method: "POST" },
    ),

  getStatus: (documentId: string) =>
    request<AnalysisStatus>(`/api/documents/${documentId}/status`),

  listDocuments: () =>
    request<{ documents: DocumentSummary[] }>("/api/documents"),

  getRequirements: (documentId: string) =>
    request<{ total: number; requirements: Requirement[] }>(
      `/api/documents/${documentId}/requirements`,
    ),

  getIssues: (documentId: string, params?: Record<string, string>) => {
    const query = params ? `?${new URLSearchParams(params).toString()}` : "";
    return request<{ total: number; issues: Issue[] }>(
      `/api/documents/${documentId}/issues${query}`,
    );
  },

  getAmbiguities: (documentId: string) =>
    request<{ total: number; ambiguities: AmbiguityFinding[] }>(
      `/api/documents/${documentId}/ambiguities`,
    ),

  getContradictions: (documentId: string) =>
    request<{ total: number; contradictions: PairFinding[] }>(
      `/api/documents/${documentId}/contradictions`,
    ),

  getDuplicates: (documentId: string) =>
    request<{ total: number; duplicates: PairFinding[] }>(
      `/api/documents/${documentId}/duplicates`,
    ),

  getMissingInformation: (documentId: string) =>
    request<{ total: number; missing_information: MissingInfoFinding[] }>(
      `/api/documents/${documentId}/missing-information`,
    ),

  getDependencies: (documentId: string) =>
    request<DependencyGraph>(`/api/documents/${documentId}/dependencies`),

  getTraceability: (documentId: string) =>
    request<{ total: number; rows: TraceabilityRow[] }>(
      `/api/documents/${documentId}/traceability`,
    ),

  getCleanRequirements: (documentId: string) =>
    request<CleanRequirementSet>(`/api/documents/${documentId}/clean-requirements`),

  exportMarkdownUrl: (documentId: string) =>
    `${BASE_URL}/api/documents/${documentId}/export?format=markdown`,

  acceptRefinement: (refinementId: string) =>
    request<{ refinement: Record<string, unknown> }>(
      `/api/refinements/${refinementId}/accept`,
      { method: "POST" },
    ),

  rejectRefinement: (refinementId: string) =>
    request<{ refinement: Record<string, unknown> }>(
      `/api/refinements/${refinementId}/reject`,
      { method: "POST" },
    ),

  editRefinement: (refinementId: string, editedText: string) =>
    request<{ refinement: Record<string, unknown> }>(`/api/refinements/${refinementId}/edit`, {
      method: "POST",
      body: JSON.stringify({ edited_text: editedText }),
    }),
};
