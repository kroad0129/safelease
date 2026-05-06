"use client";

import { useRouter } from "next/navigation";
import {
  createContext,
  ReactNode,
  useContext,
  useMemo,
  useState,
} from "react";
import { askContractChat, resolveArtifactUrl, verifyContract } from "@/lib/api";
import type { ChatMessage, VerifyResponse } from "@/types/contract";

type ContractFlowContextValue = {
  selectedFile: File | null;
  selectedFileName: string | null;
  submitting: boolean;
  errorMessage: string | null;
  result: VerifyResponse | null;
  previewMode: "image" | "pdf";
  highlightedImageUrl: string | null;
  highlightedPdfUrl: string | null;
  chatInput: string;
  chatMessages: ChatMessage[];
  chatLoading: boolean;
  chatError: string | null;
  setSelectedFile: (file: File | null) => void;
  setPreviewMode: (mode: "image" | "pdf") => void;
  setChatInput: (value: string) => void;
  startAnalysis: () => Promise<void>;
  askChatbot: (question: string) => Promise<void>;
  resetFlow: () => void;
};

const ContractFlowContext = createContext<ContractFlowContextValue | null>(null);

export function ContractFlowProvider({ children }: { children: ReactNode }) {
  const router = useRouter();
  const [selectedFile, setSelectedFileState] = useState<File | null>(null);
  const [selectedFileName, setSelectedFileName] = useState<string | null>(() => {
    if (typeof window === "undefined") {
      return null;
    }
    return window.sessionStorage.getItem("safelease.fileName");
  });
  const [submitting, setSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [result, setResult] = useState<VerifyResponse | null>(() => {
    if (typeof window === "undefined") {
      return null;
    }
    const storedResult = window.sessionStorage.getItem("safelease.result");
    return storedResult ? (JSON.parse(storedResult) as VerifyResponse) : null;
  });
  const [previewMode, setPreviewMode] = useState<"image" | "pdf">("image");
  const [chatInput, setChatInput] = useState("");
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([]);
  const [chatLoading, setChatLoading] = useState(false);
  const [chatError, setChatError] = useState<string | null>(null);

  const highlightedImageUrl = useMemo(
    () => resolveArtifactUrl(result?.artifacts.highlightedImageUrl),
    [result]
  );
  const highlightedPdfUrl = useMemo(
    () => resolveArtifactUrl(result?.artifacts.highlightedPdfUrl),
    [result]
  );

  const setSelectedFile = (file: File | null) => {
    setSelectedFileState(file);
    setSelectedFileName(file?.name ?? null);
    setErrorMessage(null);
  };

  const startAnalysis = async () => {
    if (!selectedFile) {
      setErrorMessage("업로드할 PDF 파일을 먼저 선택해주세요.");
      return;
    }

    setSubmitting(true);
    setErrorMessage(null);
    setResult(null);
    setChatInput("");
    setChatMessages([]);
    setChatError(null);
    window.sessionStorage.removeItem("safelease.result");
    window.sessionStorage.setItem("safelease.fileName", selectedFile.name);
    router.push("/analyzing");

    try {
      const nextResult = await verifyContract(selectedFile);
      setResult(nextResult);
      setPreviewMode(nextResult.artifacts.highlightedImageUrl ? "image" : "pdf");
      window.sessionStorage.setItem("safelease.result", JSON.stringify(nextResult));
      router.push("/result");
    } catch (error) {
      setResult(null);
      setErrorMessage(error instanceof Error ? error.message : "알 수 없는 오류가 발생했습니다.");
      router.push("/");
    } finally {
      setSubmitting(false);
    }
  };

  const askChatbot = async (question: string) => {
    const trimmedQuestion = question.trim();
    const combinedResultUrl = result?.artifacts.combinedResultJsonUrl;
    if (!trimmedQuestion || !combinedResultUrl) {
      return;
    }

    setChatMessages((current) => [...current, { role: "user", content: trimmedQuestion }]);
    setChatInput("");
    setChatLoading(true);
    setChatError(null);

    try {
      const answer = await askContractChat({
        combinedResultUrl,
        question: trimmedQuestion,
        history: chatMessages,
      });

      setChatMessages((current) => [
        ...current,
        {
          role: "assistant",
          content: answer.answer,
          response: answer,
        },
      ]);
    } catch (error) {
      setChatError(error instanceof Error ? error.message : "알 수 없는 오류가 발생했습니다.");
    } finally {
      setChatLoading(false);
    }
  };

  const resetFlow = () => {
    setSelectedFileState(null);
    setSelectedFileName(null);
    setSubmitting(false);
    setErrorMessage(null);
    setResult(null);
    setPreviewMode("image");
    setChatInput("");
    setChatMessages([]);
    setChatError(null);
    window.sessionStorage.removeItem("safelease.result");
    window.sessionStorage.removeItem("safelease.fileName");
    router.push("/");
  };

  return (
    <ContractFlowContext.Provider
      value={{
        selectedFile,
        selectedFileName,
        submitting,
        errorMessage,
        result,
        previewMode,
        highlightedImageUrl,
        highlightedPdfUrl,
        chatInput,
        chatMessages,
        chatLoading,
        chatError,
        setSelectedFile,
        setPreviewMode,
        setChatInput,
        startAnalysis,
        askChatbot,
        resetFlow,
      }}
    >
      {children}
    </ContractFlowContext.Provider>
  );
}

export function useContractFlow() {
  const context = useContext(ContractFlowContext);
  if (!context) {
    throw new Error("useContractFlow must be used within ContractFlowProvider");
  }
  return context;
}
