export type ReviewLevel = "양호" | "보통" | "주의";
export type SummaryReviewLevel = ReviewLevel | "확인불가";

export type LegalBasisDetail = {
  basis: string;
  title?: string;
  law_name?: string;
  article_no?: number | string | null;
  article_branch_no?: number | string | null;
  text?: string | null;
  source_name?: string | null;
  similarity?: number | string | null;
  relevance?: "direct" | "supporting" | "irrelevant";
  confidence?: "high" | "medium" | "low";
  why_relevant?: string;
};

export type Finding = {
  code: string;
  severity: string;
  title: string;
  message: string;
  field_path?: string;
  review_level?: ReviewLevel;
};

export type RagCondition = {
  label: string;
  judgment: string;
  review_level?: ReviewLevel;
  reason: string;
  legal_basis?: string[];
  legal_basis_details?: LegalBasisDetail[];
  practical_notes?: string[];
};

export type RagSpecialTerm = {
  order: number;
  label: string;
  judgment: string;
  review_level?: ReviewLevel;
  reason: string;
  legal_basis?: string[];
  legal_basis_details?: LegalBasisDetail[];
  practical_notes?: string[];
  suggested_revision?: string;
};

export type RentReferenceVerification = {
  status?: string;
  data?: {
    input?: {
      umdNm?: string | null;
      area?: number;
      areaBandLabel?: string;
      deposit?: number;
      monthlyRent?: number;
      moneyUnit?: string;
    };
    contractConvertedMonthlyRent?: {
      value?: number;
      unit?: string;
    };
    reference?: {
      basis?: string;
      fallbackUsed?: boolean;
      confidence?: string;
      sampleCount?: number;
      normalRange?: {
        min?: number;
        max?: number;
        unit?: string;
      };
      medianConvertedMonthlyRent?: {
        value?: number;
        unit?: string;
      };
      p90ConvertedMonthlyRent?: {
        value?: number;
        unit?: string;
      };
    };
    comparison?: {
      status?: string;
      level?: string;
      message?: string;
    };
    meta?: {
      formula?: string;
      conversionRate?: number;
    };
  };
  error_code?: string | null;
  error_message?: string | null;
};

export type VerifyResponse = {
  artifacts: {
    highlightedPdfUrl?: string | null;
    highlightedImageUrl?: string | null;
    renderedImageUrl?: string | null;
    extractionJsonUrl?: string | null;
    highlightJsonUrl?: string | null;
    analysisJsonUrl?: string | null;
    verificationJsonUrl?: string | null;
    combinedResultJsonUrl?: string | null;
    ragResultJsonUrl?: string | null;
    ragPayloadJsonUrl?: string | null;
    ragAnalysisJsonUrl?: string | null;
  };
  ragAnalysis?: {
    status?: string;
    embeddingModel?: string;
    analysisModel?: string;
    errorMessage?: string;
    summary?: {
      contract_conditions?: RagCondition[];
      special_terms?: RagSpecialTerm[];
      overall_summary?: {
        key_risks?: string[];
        key_strengths?: string[];
        recommended_next_actions?: string[];
      };
    };
  } | null;
  ragReview?: {
    status?: string;
    headline?: string;
    summaryText?: string;
    keyRisks?: string[];
    keyStrengths?: string[];
    recommendedNextActions?: string[];
    contractConditionCount?: number;
    specialTermCount?: number;
  } | null;
  review: {
    headline: string;
    reviewLevel: ReviewLevel;
    reviewText: string;
    findingCount: number;
    passedChecks: string[];
    inputSummary?: Record<string, unknown>;
  };
  result: {
    verification: {
      rent_reference_verification?: RentReferenceVerification;
      analysis: {
        summary: {
          overall_status: string;
          error_count: number;
          warning_count: number;
          info_count: number;
          finding_count: number;
          review_level?: ReviewLevel;
        };
        findings: Finding[];
      };
      input_summary?: Record<string, unknown>;
    };
  };
};

export type ContractChatResponse = {
  intent: string;
  answer: string;
  related_contract_points: string[];
  recommended_clauses: {
    title: string;
    clause_text: string;
    why: string;
    tenant_benefit: string;
    negotiation_note: string;
  }[];
  legal_basis: {
    basis: string;
    title: string;
    text: string;
    relevance: "direct" | "supporting";
  }[];
  cautions: string[];
  follow_up_questions: string[];
};

export type ChatMessage = {
  role: "user" | "assistant";
  content: string;
  response?: ContractChatResponse;
};
