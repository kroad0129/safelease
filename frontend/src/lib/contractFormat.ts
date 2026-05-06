import type { Finding, ReviewLevel, SummaryReviewLevel, VerifyResponse } from "@/types/contract";

const FIELD_LABELS: Record<string, string> = {
  "property.address": "소재지 확인",
  "property.leased_part.raw_text": "임대할 부분 확인",
  "lessor.address": "임대인 주소 확인",
  "lessee.address": "임차인 주소 확인",
  "broker.registration_number": "중개업 등록번호 확인",
  "broker.office_address": "중개업 소재지 확인",
  "broker.office_name": "중개업 상호 확인",
  "broker.representative_name": "중개업 대표 확인",
};

export function reviewLevelClassName(level?: SummaryReviewLevel): string {
  if (level === "확인불가") {
    return "badge unknown";
  }
  if (level === "주의") {
    return "badge danger";
  }
  if (level === "보통") {
    return "badge warn";
  }
  return "badge good";
}

export function displayReviewLevel(item: { review_level?: ReviewLevel; judgment?: string }): ReviewLevel {
  const judgment = item.judgment ?? "";
  if (["불리", "주의", "확인 필요", "위험", "불명확", "분쟁"].some((token) => judgment.includes(token))) {
    return "주의";
  }
  if (["중립", "보통", "확인 권장"].some((token) => judgment.includes(token))) {
    return "보통";
  }
  if (["유리", "양호", "무난", "문제 없음", "적정"].some((token) => judgment.includes(token))) {
    return "양호";
  }
  return item.review_level ?? "보통";
}

export function ragReviewLevel(ragReview?: VerifyResponse["ragReview"]): ReviewLevel {
  if (ragReview?.status === "failed") {
    return "주의";
  }
  if (ragReview?.keyRisks?.length) {
    return "주의";
  }
  if (ragReview?.recommendedNextActions?.length) {
    return "보통";
  }
  if (ragReview?.status === "success") {
    return "양호";
  }
  return "보통";
}

export function formatPassedChecks(checks: string[]): string[] {
  return checks.map((item) => FIELD_LABELS[item] ?? item);
}

export function formatFindingTitle(finding: Finding): string {
  if (finding.field_path && FIELD_LABELS[finding.field_path]) {
    const base = FIELD_LABELS[finding.field_path];
    if (finding.review_level === "양호") {
      return base;
    }
    if (finding.field_path === "lessor.address") {
      return "임대인 주소 확인 필요";
    }
    if (finding.field_path === "property.leased_part.raw_text") {
      return "임대할 부분 확인 필요";
    }
    if (finding.field_path === "broker.representative_name") {
      return "중개업 대표 확인 필요";
    }
    return base;
  }

  return finding.title
    .replace("lessor_address", "임대인 주소")
    .replace("property_leased_part", "임대할 부분")
    .replace("broker_representative_name", "중개업 대표");
}

export function formatManwon(value?: number): string {
  if (typeof value !== "number" || Number.isNaN(value)) {
    return "-";
  }
  return `${value.toLocaleString("ko-KR", { maximumFractionDigits: 1 })}만원`;
}

export function formatWon(value?: number): string {
  if (typeof value !== "number" || Number.isNaN(value)) {
    return "-";
  }
  return `${value.toLocaleString("ko-KR")}원`;
}

export function clampPercent(value: number): number {
  return Math.min(100, Math.max(0, value));
}

export function buildRentScale(values: number[]): { min: number; max: number } {
  const validValues = values.filter((value) => typeof value === "number" && Number.isFinite(value));
  if (!validValues.length) {
    return { min: 0, max: 100 };
  }

  const minValue = Math.min(...validValues);
  const maxValue = Math.max(...validValues);
  const spread = Math.max(maxValue - minValue, maxValue * 0.25, 20);
  const min = Math.max(0, Math.floor((minValue - spread * 0.35) / 10) * 10);
  const max = Math.ceil((maxValue + spread * 0.25) / 10) * 10;
  return { min, max: Math.max(max, min + 20) };
}
