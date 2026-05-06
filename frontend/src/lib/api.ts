import type { ChatMessage, ContractChatResponse, VerifyResponse } from "@/types/contract";

export const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

export function resolveArtifactUrl(path?: string | null): string | null {
  if (!path) {
    return null;
  }

  try {
    return new URL(path, API_BASE).toString();
  } catch {
    return null;
  }
}

export async function verifyContract(file: File): Promise<VerifyResponse> {
  const formData = new FormData();
  formData.append("file", file);

  const response = await fetch(`${API_BASE}/api/contracts/verify`, {
    method: "POST",
    body: formData,
  });

  const payload = (await response.json()) as VerifyResponse | { detail?: string };
  if (!response.ok) {
    throw new Error(
      typeof payload === "object" && payload && "detail" in payload && payload.detail
        ? payload.detail
        : "검증 처리 중 오류가 발생했습니다."
    );
  }

  return payload as VerifyResponse;
}

export async function askContractChat(params: {
  combinedResultUrl: string;
  question: string;
  history: ChatMessage[];
}): Promise<ContractChatResponse> {
  const response = await fetch(`${API_BASE}/api/contracts/chat`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      combined_result_url: params.combinedResultUrl,
      question: params.question,
      history: params.history.map((message) => ({
        role: message.role,
        content: message.content,
      })),
    }),
  });

  const payload = (await response.json()) as ContractChatResponse | { detail?: string };
  if (!response.ok) {
    throw new Error(
      typeof payload === "object" && payload && "detail" in payload && payload.detail
        ? payload.detail
        : "챗봇 답변 생성 중 오류가 발생했습니다."
    );
  }

  return payload as ContractChatResponse;
}
