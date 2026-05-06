"use client";

import type { ChangeEvent, FormEvent } from "react";
import { UploadCard } from "@/components/UploadCard";
import { useContractFlow } from "@/context/ContractFlowProvider";

export default function UploadPage() {
  const {
    selectedFile,
    submitting,
    errorMessage,
    setSelectedFile,
    startAnalysis,
  } = useContractFlow();

  const handleFileChange = (event: ChangeEvent<HTMLInputElement>) => {
    setSelectedFile(event.target.files?.[0] ?? null);
  };

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    await startAnalysis();
  };

  return (
    <main className="page-shell upload-page-shell">
      <UploadCard
        selectedFile={selectedFile}
        submitting={submitting}
        errorMessage={errorMessage}
        onFileChange={handleFileChange}
        onSubmit={handleSubmit}
      />
    </main>
  );
}
