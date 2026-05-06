import type { Metadata } from "next";
import type { ReactNode } from "react";
import { ContractFlowProvider } from "@/context/ContractFlowProvider";
import "./globals.css";

export const metadata: Metadata = {
  title: "SafeLease Review",
  description: "PDF 계약서 업로드와 하이라이트 검토 테스트 화면",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: ReactNode;
}>) {
  return (
    <html lang="ko">
      <body>
        <ContractFlowProvider>{children}</ContractFlowProvider>
      </body>
    </html>
  );
}
