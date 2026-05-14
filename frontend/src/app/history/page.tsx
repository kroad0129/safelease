"use client";

import { useEffect, useState } from "react";
import { fetchContractHistory } from "@/lib/api";
import type { ContractHistoryItem } from "@/types/contract";
import { useContractFlow } from "@/context/ContractFlowProvider";

export default function HistoryPage() {
  const { loadHistoryResult } = useContractFlow();
  const [items, setItems] = useState<ContractHistoryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadingId, setLoadingId] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;

    fetchContractHistory()
      .then((nextItems) => {
        if (mounted) {
          setItems(nextItems);
        }
      })
      .catch((error) => {
        if (mounted) {
          setErrorMessage(error instanceof Error ? error.message : "검토 기록을 불러오지 못했습니다.");
        }
      })
      .finally(() => {
        if (mounted) {
          setLoading(false);
        }
      });

    return () => {
      mounted = false;
    };
  }, []);

  const handleOpen = async (historyId: string) => {
    setLoadingId(historyId);
    setErrorMessage(null);
    try {
      await loadHistoryResult(historyId);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "검토 기록을 열지 못했습니다.");
      setLoadingId(null);
    }
  };

  return (
    <main className="history-debug-page">
      <section className="history-debug-panel">
        {loading ? <p>loading...</p> : null}
        {errorMessage ? <p className="error-text">{errorMessage}</p> : null}

        {!loading && !items.length ? (
          <p>no outputs</p>
        ) : null}

        <div className="history-debug-list">
          {items.map((item) => (
            <button
              key={item.id}
              type="button"
              className="history-debug-item"
              onClick={() => handleOpen(item.id)}
              disabled={loadingId === item.id}
            >
              {loadingId === item.id ? `${item.id} loading...` : item.id}
            </button>
          ))}
        </div>
      </section>
    </main>
  );
}
