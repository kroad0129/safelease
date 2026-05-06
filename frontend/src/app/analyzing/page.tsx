"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useContractFlow } from "@/context/ContractFlowProvider";

const loadingTips = [
  "잔금 송금 전, 등기부등본을 다시 확인하세요.",
  "임대인 이름과 등기상 소유자명이 같은지 확인하세요.",
  "주변 실거래가와 전세가율을 확인하세요.",
  "선순위 권리관계와 선순위 보증금을 확인하세요.",
  "입주 후 전입신고와 확정일자를 챙기세요.",
  "전세보증금반환보증 가입 가능 여부를 확인하세요.",
];

const progressSteps = [
  { afterSeconds: 0, message: "계약서에서 데이터를 추출하고 있어요" },
  { afterSeconds: 20, message: "계약서 내용을 검토하고 있어요" },
  { afterSeconds: 50, message: "주의할 부분을 정리하고 있어요" },
  { afterSeconds: 65, message: "거의 다 끝나가요!" },
];

export default function AnalyzingPage() {
  const router = useRouter();
  const { submitting, result, errorMessage } = useContractFlow();
  const [tipIndex, setTipIndex] = useState(0);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const progressIndex = progressSteps.reduce(
    (activeIndex, step, index) => (elapsedSeconds >= step.afterSeconds ? index : activeIndex),
    0
  );

  useEffect(() => {
    if (!submitting && result) {
      router.replace("/result");
    }
    if (!submitting && !result && !errorMessage) {
      router.replace("/");
    }
  }, [submitting, result, errorMessage, router]);

  useEffect(() => {
    const timer = window.setInterval(() => {
      setTipIndex((current) => (current + 1) % loadingTips.length);
    }, 5000);

    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    const timer = window.setInterval(() => {
      setElapsedSeconds((current) => current + 1);
    }, 1000);

    return () => window.clearInterval(timer);
  }, []);

  return (
    <main className="page-shell analysis-page-shell">
      <section className="analysis-card">
        <div className="document-loader" aria-hidden="true">
          <div className="loader-document">
            <span />
            <span />
            <span />
          </div>
          <div className="loader-magnifier" />
        </div>
        <div className="loading-tip" aria-live="polite">
          <span key={tipIndex}>{loadingTips[tipIndex]}</span>
        </div>
        <p key={progressIndex} className="loading-phase" aria-live="polite">
          {progressSteps[Math.max(progressIndex, 0)].message}
          <span aria-hidden="true" />
        </p>
      </section>
    </main>
  );
}
