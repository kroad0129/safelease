"use client";

import type { CSSProperties, FormEvent } from "react";
import { useEffect, useMemo, useRef, useState } from "react";
import { ChatBlock } from "@/components/ChatBlock";
import { LegalBasisDetails } from "@/components/LegalBasisDetails";
import { PreviewPanel } from "@/components/PreviewPanel";
import { RentReferenceBar } from "@/components/RentReferenceBar";
import {
  displayReviewLevel,
  formatFindingTitle,
  reviewLevelClassName,
} from "@/lib/contractFormat";
import type { ChatMessage, Finding, SummaryReviewLevel, VerifyResponse } from "@/types/contract";

type ResultTabsProps = {
  result: VerifyResponse;
  previewMode: "image" | "pdf";
  highlightedImageUrl: string | null;
  highlightedPdfUrl: string | null;
  chatInput: string;
  chatMessages: ChatMessage[];
  chatLoading: boolean;
  chatError: string | null;
  onPreviewModeChange: (mode: "image" | "pdf") => void;
  onChatInputChange: (value: string) => void;
  onAsk: (question: string) => Promise<void>;
  onReset: () => void;
};

type SummaryField = {
  label: string;
  value: string;
  fieldPath: string;
};

type SummaryGroup = {
  title: string;
  fields: SummaryField[];
};

type RightPanelTab = "rag" | "summary" | "conditions" | "special";

const emptyValue = "-";

const rightPanelTabs: { id: RightPanelTab; label: string }[] = [
  { id: "rag", label: "계약서 종합 요약" },
  { id: "summary", label: "계약서 핵심" },
  { id: "conditions", label: "계약내용" },
  { id: "special", label: "특약사항" },
];

export function ResultTabs({
  result,
  previewMode,
  highlightedImageUrl,
  highlightedPdfUrl,
  chatInput,
  chatMessages,
  chatLoading,
  chatError,
  onPreviewModeChange,
  onChatInputChange,
  onAsk,
  onReset,
}: ResultTabsProps) {
  const [chatOpen, setChatOpen] = useState(false);
  const [chatHintVisible, setChatHintVisible] = useState(true);
  const [activeRightTab, setActiveRightTab] = useState<RightPanelTab>("rag");
  const [robotEyeOffset, setRobotEyeOffset] = useState({ x: 0, y: 0 });
  const chatLauncherRef = useRef<HTMLButtonElement | null>(null);
  const findings = result.result.verification.analysis.findings ?? [];
  const ragReview = result.ragReview;
  const ragAnalysis = result.ragAnalysis;
  const ragConditions = ragAnalysis?.summary?.contract_conditions ?? [];
  const ragSpecialTerms = ragAnalysis?.summary?.special_terms ?? [];
  const rentReference = result.result.verification.rent_reference_verification;
  const summaryGroups = useMemo(
    () => buildSummaryGroups(result.review.inputSummary ?? result.result.verification.input_summary ?? {}),
    [result.review.inputSummary, result.result.verification.input_summary]
  );

  const handleChatSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    await onAsk(chatInput);
  };

  useEffect(() => {
    if (chatOpen) {
      return;
    }

    const handleWindowMouseMove = (event: globalThis.MouseEvent) => {
      const launcher = chatLauncherRef.current;
      if (!launcher) {
        return;
      }
      const rect = launcher.getBoundingClientRect();
      const centerX = rect.left + rect.width / 2;
      const centerY = rect.top + rect.height / 2;
      const distanceX = event.clientX - centerX;
      const distanceY = event.clientY - centerY;
      const distance = Math.hypot(distanceX, distanceY) || 1;
      const maxX = 2.5;
      const maxY = 2;
      setRobotEyeOffset({
        x: (distanceX / distance) * maxX,
        y: (distanceY / distance) * maxY,
      });
    };

    window.addEventListener("mousemove", handleWindowMouseMove);
    return () => window.removeEventListener("mousemove", handleWindowMouseMove);
  }, [chatOpen]);

  return (
    <section className="result-page">
      <div className="result-workspace">
        <PreviewPanel
          submitting={false}
          previewMode={previewMode}
          highlightedImageUrl={highlightedImageUrl}
          highlightedPdfUrl={highlightedPdfUrl}
          onPreviewModeChange={onPreviewModeChange}
          onReset={onReset}
        />

        <aside className="result-summary-panel" aria-label="계약서 분석 요약">
          <nav className="right-panel-tabs" aria-label="분석 결과 보기">
            {rightPanelTabs.map((tab) => (
              <button
                key={tab.id}
                type="button"
                className={activeRightTab === tab.id ? "active" : ""}
                onClick={() => setActiveRightTab(tab.id)}
              >
                {tab.label}
              </button>
            ))}
          </nav>

          <div key={activeRightTab} className="tab-content-page">
            {activeRightTab === "rag" ? <RagSummary ragReview={ragReview} /> : null}
            {activeRightTab === "summary" ? (
              <>
                <ContractSummary groups={summaryGroups} findings={findings} />
                <RentReferenceBar rentReference={rentReference} />
              </>
            ) : null}
            {activeRightTab === "conditions" ? <ConditionsSection conditions={ragConditions} /> : null}
            {activeRightTab === "special" ? <SpecialTermsSection specialTerms={ragSpecialTerms} /> : null}
          </div>
        </aside>
      </div>

      {result.artifacts.combinedResultJsonUrl ? (
        <div className="floating-chat">
          {chatOpen ? (
            <div className="floating-chat-panel">
              <ChatBlock
                chatInput={chatInput}
                chatMessages={chatMessages}
                chatLoading={chatLoading}
                chatError={chatError}
                onInputChange={onChatInputChange}
                onAsk={onAsk}
                onSubmit={handleChatSubmit}
              />
            </div>
          ) : null}
          {!chatOpen && chatHintVisible ? (
            <div className="chat-hint-bubble" role="status">
              <p>궁금한 조항이 있나요? 세리에게 편하게 물어보세요.</p>
              <button
                type="button"
                aria-label="세리 안내 말풍선 닫기"
                onClick={() => setChatHintVisible(false)}
              >
                ×
              </button>
            </div>
          ) : null}
          <button
            ref={chatLauncherRef}
            type="button"
            className={chatOpen ? "chat-launcher open" : "chat-launcher"}
            onClick={() => {
              setRobotEyeOffset({ x: 0, y: 0 });
              setChatOpen((current) => !current);
            }}
            aria-label={chatOpen ? "Q&A 닫기" : "Q&A 열기"}
            style={
              {
                "--eye-x": `${robotEyeOffset.x}px`,
                "--eye-y": `${robotEyeOffset.y}px`,
              } as CSSProperties
            }
          >
            <span className="robot-face" aria-hidden="true">
              <span className="robot-antenna" />
              <span className="robot-eye left" />
              <span className="robot-eye right" />
              <span className="robot-mouth" />
            </span>
          </button>
        </div>
      ) : null}
    </section>
  );
}

function ContractSummary({ groups, findings }: { groups: SummaryGroup[]; findings: Finding[] }) {
  const visibleFindings = findings.filter((finding) => !isRentReferenceFinding(finding));
  const remainingFindings = visibleFindings.filter(
    (finding) => !groups.some((group) => group.fields.some((field) => field.fieldPath === finding.field_path))
  );

  return (
    <div className="review-block">
      <div className="section-title-row">
        <h3>계약서 핵심 확인</h3>
        <span className="subtle-count">{visibleFindings.length ? `주의 ${visibleFindings.length}건` : "주요 이상 없음"}</span>
      </div>
      <div className="contract-summary-grid">
        <div className="summary-stack">
          {groups.slice(0, 3).map((group) => (
            <SummaryCard key={group.title} group={group} findings={visibleFindings} />
          ))}
        </div>
        <SummaryCard group={groups[3]} findings={visibleFindings} />
      </div>
      {remainingFindings.length ? (
        <ul className="finding-list inline-top-space">
          {remainingFindings.map((finding) => (
            <li key={finding.code} className="finding-item compact-finding">
              <div className="finding-head">
                <span className={reviewLevelClassName(finding.review_level)}>{finding.review_level}</span>
                <strong>{formatFindingTitle(finding)}</strong>
              </div>
              <p>{finding.message}</p>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

function SummaryCard({ group, findings }: { group: SummaryGroup; findings: Finding[] }) {
  return (
    <section className="summary-card">
      <h4>{group.title}</h4>
      <dl>
        {group.fields.map((field) => {
          const finding = findings.find((item) => item.field_path === field.fieldPath);
          const level = fieldReviewLevel(field.fieldPath, findings, field.value);
          return (
            <div key={field.fieldPath}>
              <dt>
                <span>{field.label}</span>
                <span className={reviewLevelClassName(level)}>{level}</span>
              </dt>
              <dd>{field.value}</dd>
              {finding ? <p className="summary-warning">{finding.message}</p> : null}
            </div>
          );
        })}
      </dl>
    </section>
  );
}

function RagSummary({ ragReview }: { ragReview: VerifyResponse["ragReview"] }) {
  const statusLabel = ragReview?.status === "success" ? "완료" : ragReview?.status === "failed" ? "실패" : "대기";

  return (
    <div className="review-block contract-overview-block">
      <div className="section-title-row">
        <h3>계약서 종합 요약</h3>
        <span className="subtle-count">{statusLabel}</span>
      </div>
      <div className="overview-hero">
        <div>
          <h4>{ragReview?.headline ?? "계약서 분석을 기다리고 있습니다."}</h4>
          <p>
            {ragReview?.summaryText ??
              "분석이 완료되면 주의할 부분, 괜찮은 부분, 먼저 할 일을 한눈에 정리해드립니다."}
          </p>
        </div>
      </div>

      <div className="overview-card-grid">
        <OverviewListCard
          tone="danger"
          title="주의할 부분"
          items={ragReview?.keyRisks ?? []}
          emptyText="크게 주의할 항목은 아직 확인되지 않았습니다."
        />
        <OverviewListCard
          tone="good"
          title="괜찮은 부분"
          items={ragReview?.keyStrengths ?? []}
          emptyText="강점으로 분류된 항목이 아직 없습니다."
        />
        <OverviewListCard
          tone="action"
          title="먼저 할 일"
          items={ragReview?.recommendedNextActions ?? []}
          emptyText="추가로 권장할 다음 행동이 없습니다."
        />
      </div>
    </div>
  );
}

function OverviewListCard({
  emptyText,
  items,
  title,
  tone,
}: {
  emptyText: string;
  items: string[];
  title: string;
  tone: "danger" | "good" | "action";
}) {
  return (
    <section className={`overview-list-card ${tone}`}>
      <h4>{title}</h4>
      {items.length ? (
        <ul>
          {items.slice(0, 4).map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      ) : (
        <p>{emptyText}</p>
      )}
    </section>
  );
}

function ConditionsSection({ conditions }: { conditions: NonNullable<VerifyResponse["ragAnalysis"]>["summary"] extends infer S ? S extends { contract_conditions?: infer C } ? C extends Array<infer I> ? I[] : never : never : never }) {
  return (
    <div className="review-block">
      <div className="section-title-row">
        <h3>계약내용 분석</h3>
        <span className="subtle-count">{conditions.length}건</span>
      </div>
      {conditions.length ? (
        <ul className="finding-list">
          {conditions.map((item) => (
            <li key={item.label} className="finding-item">
              <div className="finding-head">
                <span className={reviewLevelClassName(displayReviewLevel(item))}>{item.judgment}</span>
                <strong>{item.label}</strong>
              </div>
              <p>{item.reason}</p>
              {item.practical_notes?.length ? (
                <p className="detail-line">더 살펴볼 점: {item.practical_notes.join(" / ")}</p>
              ) : null}
              <LegalBasisDetails details={item.legal_basis_details} />
            </li>
          ))}
        </ul>
      ) : (
        <p className="muted-text">아직 표시할 계약내용 분석이 없습니다.</p>
      )}
    </div>
  );
}

function SpecialTermsSection({ specialTerms }: { specialTerms: NonNullable<VerifyResponse["ragAnalysis"]>["summary"] extends infer S ? S extends { special_terms?: infer C } ? C extends Array<infer I> ? I[] : never : never : never }) {
  return (
    <div className="review-block">
      <div className="section-title-row">
        <h3>특약 분석</h3>
        <span className="subtle-count">{specialTerms.length}건</span>
      </div>
      {specialTerms.length ? (
        <ul className="finding-list">
          {specialTerms.map((item) => (
            <li key={item.order} className="finding-item">
              <div className="finding-head">
                <span className={reviewLevelClassName(displayReviewLevel(item))}>{item.judgment}</span>
                <strong>{item.label}</strong>
              </div>
              <p>{item.reason}</p>
              {item.suggested_revision ? <p className="detail-line">권장 수정문: {item.suggested_revision}</p> : null}
              <LegalBasisDetails details={item.legal_basis_details} />
            </li>
          ))}
        </ul>
      ) : (
        <p className="muted-text">아직 표시할 특약 분석이 없습니다.</p>
      )}
    </div>
  );
}

function buildSummaryGroups(inputSummary: Record<string, unknown>): SummaryGroup[] {
  const property = readObject(inputSummary.property);
  const lessor = readObject(inputSummary.lessor);
  const lessee = readObject(inputSummary.lessee);
  const broker = readObject(inputSummary.broker);

  return [
    {
      title: "부동산 표시",
      fields: [
        { label: "소재지", value: readText(property.address), fieldPath: "property.address" },
        {
          label: "임대할 부분",
          value: readText(property.leased_part_raw),
          fieldPath: "property.leased_part.raw_text",
        },
      ],
    },
    {
      title: "임차인",
      fields: [{ label: "주소", value: readText(lessee.address), fieldPath: "lessee.address" }],
    },
    {
      title: "임대인",
      fields: [{ label: "주소", value: readText(lessor.address), fieldPath: "lessor.address" }],
    },
    {
      title: "중개업자",
      fields: [
        { label: "사무소 소재지", value: readText(broker.office_address), fieldPath: "broker.office_address" },
        { label: "사무소 명칭", value: readText(broker.office_name), fieldPath: "broker.office_name" },
        { label: "대표", value: readText(broker.representative_name), fieldPath: "broker.representative_name" },
        { label: "등록번호", value: readText(broker.registration_number), fieldPath: "broker.registration_number" },
      ],
    },
  ];
}

function readObject(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

function readText(value: unknown): string {
  if (typeof value === "string" && value.trim()) {
    return value;
  }
  if (typeof value === "number" && Number.isFinite(value)) {
    return value.toLocaleString("ko-KR");
  }
  return emptyValue;
}

function fieldReviewLevel(fieldPath: string, findings: Finding[], value: string): SummaryReviewLevel {
  const finding = findings.find((item) => item.field_path === fieldPath);
  if (finding?.review_level) {
    return finding.review_level;
  }
  if (fieldPath.startsWith("broker.") && fieldPath !== "broker.registration_number") {
    const brokerLookupFinding = findings.find(
      (item) =>
        item.field_path === "broker.registration_number" &&
        item.review_level === "주의" &&
        (item.code === "BROKER_NOT_FOUND" ||
          item.code === "BROKER_QUERY_FAILED" ||
          item.title.includes("조회 결과 없음") ||
          item.title.includes("조회 실패"))
    );
    if (brokerLookupFinding) {
      return "확인불가";
    }
  }
  return value === emptyValue ? "보통" : "양호";
}

function isRentReferenceFinding(finding: Finding): boolean {
  return finding.title === "임대료 참고 범위 초과" || finding.code === "RENT_REFERENCE_HIGH";
}
