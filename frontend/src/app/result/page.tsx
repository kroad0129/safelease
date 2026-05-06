"use client";

import { useRouter } from "next/navigation";
import { ResultTabs } from "@/components/ResultTabs";
import { useContractFlow } from "@/context/ContractFlowProvider";

export default function ResultPage() {
  const router = useRouter();
  const flow = useContractFlow();

  if (!flow.result) {
    return (
      <main className="page-shell result-empty-shell">
        <section className="review-block emphasis">
          <h1>표시할 분석 결과가 없습니다.</h1>
          <p>계약서를 먼저 업로드하면 결과 페이지에서 탭별로 확인할 수 있습니다.</p>
          <button className="primary-button" type="button" onClick={() => router.push("/")}>
            계약서 업로드하기
          </button>
        </section>
      </main>
    );
  }

  return (
    <main className="page-shell">
      <ResultTabs
        result={flow.result}
        previewMode={flow.previewMode}
        highlightedImageUrl={flow.highlightedImageUrl}
        highlightedPdfUrl={flow.highlightedPdfUrl}
        chatInput={flow.chatInput}
        chatMessages={flow.chatMessages}
        chatLoading={flow.chatLoading}
        chatError={flow.chatError}
        onPreviewModeChange={flow.setPreviewMode}
        onChatInputChange={flow.setChatInput}
        onAsk={flow.askChatbot}
        onReset={flow.resetFlow}
      />
    </main>
  );
}
