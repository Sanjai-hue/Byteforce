-- ReqGuard AI — core schema
-- All tables are server-owned: the FastAPI backend is the only writer, using the
-- project admin API key. RLS is enabled with no permissive policies so that the
-- public anon key cannot read or write any of this data directly.

CREATE EXTENSION IF NOT EXISTS vector;

-- ---------------------------------------------------------------------------
-- documents
-- ---------------------------------------------------------------------------
CREATE TABLE public.documents (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    filename      TEXT        NOT NULL,
    file_url      TEXT,
    storage_key   TEXT,
    file_type     TEXT        NOT NULL,
    file_size     BIGINT      NOT NULL,
    status        TEXT        NOT NULL DEFAULT 'uploaded',
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT documents_status_check CHECK (
        status IN ('uploaded', 'extracting', 'analyzing', 'completed', 'failed')
    ),
    CONSTRAINT documents_file_type_check CHECK (
        file_type IN ('pdf', 'docx', 'txt')
    )
);

-- ---------------------------------------------------------------------------
-- requirements
-- ---------------------------------------------------------------------------
CREATE TABLE public.requirements (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id      UUID        NOT NULL REFERENCES public.documents(id) ON DELETE CASCADE,
    requirement_code TEXT        NOT NULL,
    original_text    TEXT        NOT NULL,
    normalized_text  TEXT        NOT NULL,
    requirement_type TEXT        NOT NULL DEFAULT 'other',
    section          TEXT,
    page_number      INTEGER,
    embedding        vector(384),
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT requirements_type_check CHECK (
        requirement_type IN ('functional', 'non_functional', 'business_rule', 'constraint', 'other')
    ),
    CONSTRAINT requirements_code_unique UNIQUE (document_id, requirement_code)
);

CREATE INDEX requirements_document_id_idx ON public.requirements (document_id);
CREATE INDEX requirements_embedding_hnsw_idx
    ON public.requirements USING hnsw (embedding vector_cosine_ops);

-- ---------------------------------------------------------------------------
-- analysis_runs
-- ---------------------------------------------------------------------------
CREATE TABLE public.analysis_runs (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id   UUID        NOT NULL REFERENCES public.documents(id) ON DELETE CASCADE,
    status        TEXT        NOT NULL DEFAULT 'pending',
    stage         TEXT,
    progress      INTEGER     NOT NULL DEFAULT 0,
    started_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at  TIMESTAMPTZ,
    error_message TEXT,
    stats         JSONB       NOT NULL DEFAULT '{}'::jsonb,
    CONSTRAINT analysis_runs_status_check CHECK (
        status IN ('pending', 'extracting', 'analyzing', 'completed', 'failed')
    ),
    CONSTRAINT analysis_runs_progress_check CHECK (progress BETWEEN 0 AND 100)
);

CREATE INDEX analysis_runs_document_id_idx ON public.analysis_runs (document_id);

-- ---------------------------------------------------------------------------
-- issues  (ambiguity, missing_information, and the headline row for pair issues)
-- ---------------------------------------------------------------------------
CREATE TABLE public.issues (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id          UUID        NOT NULL REFERENCES public.documents(id) ON DELETE CASCADE,
    requirement_id       UUID        REFERENCES public.requirements(id) ON DELETE CASCADE,
    issue_type           TEXT        NOT NULL,
    severity             TEXT        NOT NULL DEFAULT 'medium',
    confidence           DOUBLE PRECISION NOT NULL DEFAULT 0,
    evidence             TEXT,
    description          TEXT,
    suggested_refinement TEXT,
    status               TEXT        NOT NULL DEFAULT 'open',
    metadata             JSONB       NOT NULL DEFAULT '{}'::jsonb,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT issues_type_check CHECK (
        issue_type IN ('ambiguity', 'contradiction', 'duplicate', 'missing_information', 'dependency')
    ),
    CONSTRAINT issues_severity_check CHECK (
        severity IN ('critical', 'high', 'medium', 'low')
    ),
    CONSTRAINT issues_status_check CHECK (
        status IN ('open', 'accepted', 'rejected', 'resolved', 'needs_review')
    ),
    CONSTRAINT issues_confidence_check CHECK (confidence BETWEEN 0 AND 1)
);

CREATE INDEX issues_document_id_idx     ON public.issues (document_id);
CREATE INDEX issues_requirement_id_idx  ON public.issues (requirement_id);
CREATE INDEX issues_type_idx            ON public.issues (document_id, issue_type);

-- ---------------------------------------------------------------------------
-- issue_relationships  (the two requirements behind a duplicate/contradiction)
-- ---------------------------------------------------------------------------
CREATE TABLE public.issue_relationships (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    issue_id         UUID NOT NULL REFERENCES public.issues(id) ON DELETE CASCADE,
    requirement_a    UUID NOT NULL REFERENCES public.requirements(id) ON DELETE CASCADE,
    requirement_b    UUID NOT NULL REFERENCES public.requirements(id) ON DELETE CASCADE,
    code_a           TEXT NOT NULL,
    code_b           TEXT NOT NULL,
    similarity_score DOUBLE PRECISION,
    classification   TEXT NOT NULL,
    conflict_type    TEXT,
    reason           TEXT,
    evidence_a       TEXT,
    evidence_b       TEXT,
    recommendation   TEXT,
    confidence       DOUBLE PRECISION NOT NULL DEFAULT 0,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX issue_relationships_issue_id_idx ON public.issue_relationships (issue_id);

-- ---------------------------------------------------------------------------
-- dependencies
-- ---------------------------------------------------------------------------
CREATE TABLE public.dependencies (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id        UUID NOT NULL REFERENCES public.documents(id) ON DELETE CASCADE,
    source_requirement UUID NOT NULL REFERENCES public.requirements(id) ON DELETE CASCADE,
    target_requirement UUID NOT NULL REFERENCES public.requirements(id) ON DELETE CASCADE,
    source_code        TEXT NOT NULL,
    target_code        TEXT NOT NULL,
    relationship       TEXT NOT NULL,
    reason             TEXT,
    confidence         DOUBLE PRECISION NOT NULL DEFAULT 0,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT dependencies_relationship_check CHECK (
        relationship IN ('depends_on', 'enables', 'requires', 'prerequisite_for')
    ),
    CONSTRAINT dependencies_no_self_loop CHECK (source_requirement <> target_requirement)
);

CREATE INDEX dependencies_document_id_idx ON public.dependencies (document_id);

-- ---------------------------------------------------------------------------
-- refinements  (original text is never overwritten; refinements live here)
-- ---------------------------------------------------------------------------
CREATE TABLE public.refinements (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    requirement_id UUID        NOT NULL REFERENCES public.requirements(id) ON DELETE CASCADE,
    document_id    UUID        NOT NULL REFERENCES public.documents(id) ON DELETE CASCADE,
    issue_id       UUID        REFERENCES public.issues(id) ON DELETE SET NULL,
    original_text  TEXT        NOT NULL,
    suggested_text TEXT        NOT NULL,
    edited_text    TEXT,
    reason         TEXT,
    status         TEXT        NOT NULL DEFAULT 'pending',
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT refinements_status_check CHECK (
        status IN ('pending', 'accepted', 'rejected', 'edited')
    )
);

CREATE INDEX refinements_requirement_id_idx ON public.refinements (requirement_id);
CREATE INDEX refinements_document_id_idx    ON public.refinements (document_id);

-- ---------------------------------------------------------------------------
-- Lock everything down: the backend uses the admin key (bypasses RLS); the
-- public anon key gets no policy, therefore no access.
-- ---------------------------------------------------------------------------
ALTER TABLE public.documents           ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.requirements        ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.analysis_runs       ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.issues              ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.issue_relationships ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.dependencies        ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.refinements         ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON public.documents           FROM anon, authenticated;
REVOKE ALL ON public.requirements        FROM anon, authenticated;
REVOKE ALL ON public.analysis_runs       FROM anon, authenticated;
REVOKE ALL ON public.issues              FROM anon, authenticated;
REVOKE ALL ON public.issue_relationships FROM anon, authenticated;
REVOKE ALL ON public.dependencies        FROM anon, authenticated;
REVOKE ALL ON public.refinements         FROM anon, authenticated;
