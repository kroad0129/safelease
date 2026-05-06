import type { LegalBasisDetail } from "@/types/contract";

export function LegalBasisDetails({ details }: { details?: LegalBasisDetail[] }) {
  const visibleDetails = (details ?? []).filter((item) => item.text);

  if (!visibleDetails.length) {
    return null;
  }

  return (
    <details className="legal-basis-panel">
      <summary>관련 법령 보기</summary>
      <div className="legal-basis-list">
        {visibleDetails.map((item) => (
          <article key={`${item.basis}-${item.title ?? ""}`} className="legal-basis-detail">
            <div className="legal-basis-title">
              <strong>{item.basis}</strong>
              {item.title ? <span>{item.title}</span> : null}
            </div>
            {item.why_relevant ? (
              <div className="legal-relevance-note">
                <span>관련성 설명</span>
                <p>{item.why_relevant}</p>
              </div>
            ) : null}
            <details className="legal-text-disclosure">
              <summary>법령 내용</summary>
              <p>{item.text}</p>
            </details>
          </article>
        ))}
      </div>
    </details>
  );
}
