/** Types mirroring the ReqGuard backend API. */

export type DocumentStatus =
  | "uploaded"
  | "extracting"
  | "analyzing"
  | "completed"
  | "failed"
  | "pending";

export type Severity = "critical" | "high" | "medium" | "low";

export type IssueType =
  | "ambiguity"
  | "contradiction"
  | "duplicate"
  | "missing_information"
  | "dependency";

export type RefinementStatus = "pending" | "accepted" | "rejected" | "edited";

export interface UploadResponse {
  document_id: string;
  filename: string;
  file_type: string;
  file_size: number;
  status: DocumentStatus;
}

export interface AnalysisStats {
  requirements?: number;
  ambiguities?: number;
  contradictions?: number;
  duplicates?: number;
  dependencies?: number;
  missing_information?: number;
  refinements?: number;
  llm_model?: string;
  embedding_model?: string;
}

export interface AnalysisStatus {
  document_id: string;
  status: DocumentStatus;
  stage: string | null;
  stage_label: string;
  progress: number;
  error_message: string | null;
  stats: AnalysisStats;
  started_at?: string;
  completed_at?: string;
}

export interface Requirement {
  id: string;
  document_id: string;
  requirement_code: string;
  original_text: string;
  normalized_text: string;
  requirement_type: string;
  section: string | null;
  page_number: number | null;
  created_at: string;
}

export interface Issue {
  id: string;
  document_id: string;
  requirement_id: string | null;
  issue_type: IssueType;
  severity: Severity;
  confidence: number;
  evidence: string | null;
  description: string | null;
  suggested_refinement: string | null;
  status: string;
  metadata: Record<string, unknown>;
  created_at: string;
}

export interface AmbiguityFinding {
  issue_id: string;
  requirement: Requirement | null;
  requirement_code: string | null;
  ambiguous_terms: string[];
  evidence: string | null;
  explanation: string | null;
  severity: Severity;
  confidence: number;
  status: string;
  suggested_refinement: string | null;
  refinement_id: string | null;
  refinement_status: RefinementStatus | null;
}

export interface PairFinding {
  issue_id: string;
  issue_type: IssueType;
  severity: Severity;
  confidence: number;
  status: string;
  description: string | null;
  classification: string | null;
  conflict_type: string | null;
  similarity_score: number | null;
  reason: string | null;
  evidence_a: string | null;
  evidence_b: string | null;
  recommendation: string | null;
  requirement_a: Requirement | null;
  requirement_b: Requirement | null;
  code_a: string | null;
  code_b: string | null;
}

export interface MissingInfoFinding {
  issue_id: string;
  requirement: Requirement | null;
  missing_information: string[];
  suggested_questions: string[];
  evidence: string | null;
  explanation: string | null;
  severity: Severity;
  confidence: number;
  suggested_refinement: string | null;
}

export interface GraphNode {
  id: string;
  code: string;
  label: string;
  original_text: string;
  requirement_type: string;
  section: string | null;
  page_number: number | null;
  connected: boolean;
}

export interface GraphEdge {
  id: string;
  source: string;
  target: string;
  source_code: string;
  target_code: string;
  relationship: string;
  reason: string | null;
  confidence: number;
}

export interface DependencyGraph {
  document_id: string;
  nodes: GraphNode[];
  edges: GraphEdge[];
  total_edges: number;
}

export interface TraceabilityIssue {
  id: string;
  type: IssueType;
  label: string;
  severity: Severity;
  confidence: number;
  evidence: string;
  description: string;
}

export interface TraceabilityRow {
  requirement_id: string;
  requirement_code: string;
  original_text: string;
  requirement_type: string;
  section: string | null;
  page_number: number | null;
  source: string;
  issues: TraceabilityIssue[];
  evidence: string;
  suggested_refinement: string | null;
  refinement_id: string | null;
  refinement_status: RefinementStatus | null;
  status: string;
}

export interface CleanRequirement {
  original_requirement_id: string;
  requirement_code: string;
  original_text: string;
  refined_text: string;
  requirement_type: string;
  section: string | null;
  page_number: number | null;
  reason: string | null;
  status: string;
  refinement_id: string | null;
  /** The suggested (or edited) rewrite, whether or not it has been accepted. */
  proposed_text: string | null;
  refinement_status: "pending" | "accepted" | "edited" | "rejected" | null;
  included: boolean;
}

export interface CleanRequirementSet {
  document_id: string;
  total: number;
  included: number;
  merged_duplicates: number;
  unresolved_contradictions: number;
  requirements: CleanRequirement[];
}

export interface DocumentSummary {
  id: string;
  filename: string;
  file_type: string;
  file_size: number;
  status: DocumentStatus;
  created_at: string;
}

export interface ApiErrorBody {
  error: { code: string; message: string };
}
