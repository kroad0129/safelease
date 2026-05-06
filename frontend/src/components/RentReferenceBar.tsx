import {
  buildRentScale,
  clampPercent,
  formatManwon,
} from "@/lib/contractFormat";
import type { ReactNode } from "react";
import type { RentReferenceVerification } from "@/types/contract";

export function RentReferenceBar({ rentReference }: { rentReference?: RentReferenceVerification }) {
  const data = rentReference?.data;
  const reference = data?.reference;
  const normalRange = reference?.normalRange;
  const contractValue = data?.contractConvertedMonthlyRent?.value;
  const normalMin = normalRange?.min;
  const normalMax = normalRange?.max;
  const median = reference?.medianConvertedMonthlyRent?.value;

  if (!rentReference || rentReference.status !== "success" || !data || typeof contractValue !== "number") {
    return (
      <div className="review-block">
        <div className="section-title-row">
          <h3>임대료 시세 비교</h3>
          <span className="subtle-count">대기</span>
        </div>
        <p className="muted-text">
          {rentReference?.error_message ?? "참고 임대료 비교 결과가 아직 없습니다."}
        </p>
      </div>
    );
  }

  const scale = buildRentScale([
    contractValue,
    normalMin ?? contractValue,
    normalMax ?? contractValue,
    median ?? contractValue,
  ]);
  const scaleRange = scale.max - scale.min;
  const toScalePercent = (value: number) => clampPercent(((value - scale.min) / scaleRange) * 100);
  const contractLeft = toScalePercent(contractValue);
  const rangeLeft = toScalePercent(normalMin ?? contractValue);
  const rangeRight = toScalePercent(normalMax ?? contractValue);
  const rangeWidth = Math.max(2, rangeRight - rangeLeft);
  const medianLeft = typeof median === "number" ? toScalePercent(median) : null;
  const comparisonLevel = data.comparison?.level === "warning" ? "보통" : "양호";
  const conversionRate = data.meta?.conversionRate ?? 0.045;

  return (
    <div className="review-block rent-reference-block">
      <div className="section-title-row">
        <h3>동네 시세 비교</h3>
      </div>

      <p className="rent-context">
        {data.input?.umdNm ?? "법정동 미상"} · {data.input?.areaBandLabel ?? "면적구간 미상"} · 최근 1년 이내
      </p>

      <div className="rent-bar" aria-label="임대료 환산월세 비교 막대">
        <div className="rent-range" style={{ left: `${rangeLeft}%`, width: `${rangeWidth}%` }} />
        {medianLeft !== null ? <div className="rent-marker median" style={{ left: `${medianLeft}%` }} /> : null}
        <div className="rent-contract-marker" style={{ left: `${contractLeft}%` }}>
          <span>{formatManwon(contractValue)}</span>
        </div>
      </div>

      <div className="rent-axis">
        <span>{formatManwon(scale.min)}</span>
        <span>{formatManwon(scale.max)}</span>
      </div>

      <div className="rent-legend">
        <span>
          <i className="legend-contract" /> 환산월세
          <HelpTooltip label="환산월세 설명">
            환산월세 = 월세 + 보증금 x {conversionRate} / 12
          </HelpTooltip>
        </span>
        <span>
          <i className="legend-range" /> 주변 시세 범위
          <HelpTooltip label="주변 시세 범위 설명">
            비슷한 면적의 최근 실거래에서 일반적으로 형성된 환산월세 구간입니다. 이 계약은{" "}
            {formatManwon(normalMin)} ~ {formatManwon(normalMax)} 사이에 있으면 주변 시세 범위로 봅니다.
          </HelpTooltip>
        </span>
      </div>

      {data.comparison?.message ? (
        <p className={`rent-message ${comparisonLevel === "보통" ? "warn" : "good"}`}>{data.comparison.message}</p>
      ) : null}
    </div>
  );
}

function HelpTooltip({ children, label }: { children: ReactNode; label: string }) {
  return (
    <span className="help-tooltip" tabIndex={0} aria-label={label}>
      ?
      <span role="tooltip">{children}</span>
    </span>
  );
}
