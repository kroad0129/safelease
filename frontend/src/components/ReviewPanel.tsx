import type { FormEvent } from "react";
import { LegalBasisDetails } from "@/components/LegalBasisDetails";
import { RentReferenceBar } from "@/components/RentReferenceBar";
import {
  displayReviewLevel,
  formatFindingTitle,
  formatPassedChecks,
  ragReviewLevel,
  reviewLevelClassName,
} from "@/lib/contractFormat";
import type { ChatMessage, VerifyResponse } from "@/types/contract";
import { ChatBlock } from "./ChatBlock";

type ReviewPanelProps = {
  response: VerifyResponse | null;
  submitting: boolean;
  chatInput: string;
  chatMessages: ChatMessage[];
  chatLoading: boolean;
  chatError: string | null;
  onChatInputChange: (value: string) => void;
  onAsk: (question: string) => void;
  onChatSubmit: (event: FormEvent<HTMLFormElement>) => void;
};

export function ReviewPanel({
  response,
  submitting,
  chatInput,
  chatMessages,
  chatLoading,
  chatError,
  onChatInputChange,
  onAsk,
  onChatSubmit,
}: ReviewPanelProps) {
  const findings = response?.result.verification.analysis.findings ?? [];
  const passedChecks = formatPassedChecks(response?.review.passedChecks ?? []);
  const ragReview = response?.ragReview;
  const ragAnalysis = response?.ragAnalysis;
  const ragConditions = ragAnalysis?.summary?.contract_conditions ?? [];
  const ragSpecialTerms = ragAnalysis?.summary?.special_terms ?? [];
  const rentReference = response?.result.verification.rent_reference_verification;

  return (
    <aside className="review-panel">
      <div className="panel-header">
        <div>
          <p className="panel-eyebrow">AI Review</p>
          <h2>검토 결과</h2>
        </div>
        <span className={reviewLevelClassName(response?.review.reviewLevel)}>
          {response?.review.reviewLevel ?? "대기"}
        </span>
      </div>

      <div className="review-block emphasis">
        <h3>{response?.review.headline ?? "PDF 업로드를 기다리는 중입니다."}</h3>
        <p>
          {response?.review.reviewText ??
            (submitting
              ? "계약서 검토를 진행하고 있습니다."
              : "업로드가 끝나면 자동 검증 요약과 LLM에 바로 연결하기 좋은 문구를 함께 보여드립니다.")}
        </p>
      </div>

      <div className="review-block">
        <div className="section-title-row">
          <h3>자동 검증</h3>
          <span className="subtle-count">{passedChecks.length + findings.length}건</span>
        </div>
        {passedChecks.length ? (
          <ul className="chip-list">
            {passedChecks.map((item) => (
              <li key={item} className="chip good-chip">
                {item}
              </li>
            ))}
          </ul>
        ) : (
          <p className="muted-text">표시할 양호 항목이 없습니다.</p>
        )}
        {findings.length ? (
          <ul className="finding-list inline-top-space">
            {findings.map((finding) => (
              <li key={finding.code} className="finding-item">
                <div className="finding-head">
                  <span className={reviewLevelClassName(finding.review_level)}>{finding.review_level}</span>
                  <strong>{formatFindingTitle(finding)}</strong>
                </div>
                <p>{finding.message}</p>
              </li>
            ))}
          </ul>
        ) : (
          <p className="muted-text">자동 검증에서 별도 이상 징후가 보이지 않았습니다.</p>
        )}
      </div>

      <RentReferenceBar rentReference={rentReference} />

      <div className="review-block emphasis">
        <div className="section-title-row">
          <h3>RAG 요약</h3>
          <span className={reviewLevelClassName(ragReviewLevel(ragReview))}>
            {ragReview?.status === "success" ? "완료" : ragReview?.status === "failed" ? "실패" : "대기"}
          </span>
        </div>
        <p>
          {ragReview?.summaryText ??
            "법령 근거 기반 분석은 업로드 후 함께 생성됩니다. 여기서 핵심 위험, 강점, 다음 조치를 빠르게 확인할 수 있습니다."}
        </p>
        {ragReview?.keyRisks?.length ? (
          <ul className="simple-list">
            {ragReview.keyRisks.slice(0, 3).map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        ) : null}
      </div>

      {response?.artifacts.combinedResultJsonUrl ? (
        <ChatBlock
          chatInput={chatInput}
          chatMessages={chatMessages}
          chatLoading={chatLoading}
          chatError={chatError}
          onInputChange={onChatInputChange}
          onAsk={onAsk}
          onSubmit={onChatSubmit}
        />
      ) : null}

      <div className="review-block">
        <div className="section-title-row">
          <h3>계약조건 분석</h3>
          <span className="subtle-count">{ragConditions.length}건</span>
        </div>
        {ragConditions.length ? (
          <ul className="finding-list">
            {ragConditions.map((item) => (
              <li key={item.label} className="finding-item">
                <div className="finding-head">
                  <span className={reviewLevelClassName(displayReviewLevel(item))}>{item.judgment}</span>
                  <strong>{item.label}</strong>
                </div>
                <p>{item.reason}</p>
                <LegalBasisDetails details={item.legal_basis_details} />
                {item.practical_notes?.length ? (
                  <p className="detail-line">더 살펴볼 점: {item.practical_notes.join(" / ")}</p>
                ) : null}
              </li>
            ))}
          </ul>
        ) : (
          <p className="muted-text">아직 표시할 계약조건 분석이 없습니다.</p>
        )}
      </div>

      <div className="review-block">
        <div className="section-title-row">
          <h3>특약 분석</h3>
          <span className="subtle-count">{ragSpecialTerms.length}건</span>
        </div>
        {ragSpecialTerms.length ? (
          <ul className="finding-list">
            {ragSpecialTerms.map((item) => (
              <li key={item.order} className="finding-item">
                <div className="finding-head">
                  <span className={reviewLevelClassName(displayReviewLevel(item))}>{item.judgment}</span>
                  <strong>{item.label}</strong>
                </div>
                <p>{item.reason}</p>
                <LegalBasisDetails details={item.legal_basis_details} />
                {item.suggested_revision ? (
                  <p className="detail-line">권장 수정문: {item.suggested_revision}</p>
                ) : null}
              </li>
            ))}
          </ul>
        ) : (
          <p className="muted-text">아직 표시할 특약 분석이 없습니다.</p>
        )}
      </div>
    </aside>
  );
}
