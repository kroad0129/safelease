"use client";

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { useContractFlow } from "@/context/ContractFlowProvider";

export default function HistoryDetailPage() {
  const params = useParams<{ historyId: string }>();
  const historyId = params.historyId;
  const { loadHistoryResult } = useContractFlow();
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  useEffect(() => {
    loadHistoryResult(historyId).catch((error) => {
      setErrorMessage(error instanceof Error ? error.message : "검토 기록을 열지 못했습니다.");
    });
  }, [historyId, loadHistoryResult]);

  return (
    <main className="page-shell result-empty-shell">
      <section className="analysis-card">
        <div className="document-loader" aria-hidden="true">
          <div className="loader-document">
            <span />
            <span />
            <span />
          </div>
          <div className="loader-magnifier" />
        </div>
        <p className="loading-title">저장된 검토 기록을 여는 중입니다.</p>
        {errorMessage ? <p className="error-text">{errorMessage}</p> : null}
      </section>
    </main>
  );
}
