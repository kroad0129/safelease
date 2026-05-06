import type { FormEvent } from "react";
import type { ChatMessage, ContractChatResponse } from "@/types/contract";

type ChatBlockProps = {
  chatInput: string;
  chatMessages: ChatMessage[];
  chatLoading: boolean;
  chatError: string | null;
  onInputChange: (value: string) => void;
  onAsk: (question: string) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
};

export function ChatBlock({
  chatInput,
  chatMessages,
  chatLoading,
  chatError,
  onInputChange,
  onAsk,
  onSubmit,
}: ChatBlockProps) {
  const quickQuestions = [
    "반려동물 키울 때 넣을 특약이 있을까?",
    "주의해야 할 조항만 쉽게 설명해줘",
    "보증금 반환에 유리한 특약을 추천해줘",
  ];

  return (
    <div className="chat-block">
      <div className={chatMessages.length ? "chat-thread" : "chat-thread empty"}>
        {chatMessages.length ? (
          chatMessages.map((message, index) => (
            <div key={`${message.role}-${index}`} className={`chat-message ${message.role}`}>
              {message.response ? (
                <AssistantResponse response={message.response} />
              ) : (
                <p>{message.content}</p>
              )}
            </div>
          ))
        ) : (
          <div className="quick-question-row in-thread">
            {quickQuestions.map((question) => (
              <button
                key={question}
                type="button"
                className="quick-question"
                onClick={() => onAsk(question)}
                disabled={chatLoading}
              >
                {question}
              </button>
            ))}
          </div>
        )}
        {chatLoading ? (
          <p className="muted-text loading-dots">
            답변을 작성하고 있습니다<span aria-hidden="true" />
          </p>
        ) : null}
      </div>
      <form className="chat-form" onSubmit={onSubmit}>
        <textarea
          value={chatInput}
          onChange={(event) => onInputChange(event.target.value)}
          placeholder="궁금한 내용을 바로 물어보세요."
          rows={1}
        />
        <button className="primary-button" type="submit" disabled={chatLoading || !chatInput.trim()}>
          질문하기
        </button>
      </form>
      {chatError ? <p className="error-text">{chatError}</p> : null}
    </div>
  );
}

function AssistantResponse({ response }: { response: ContractChatResponse }) {
  const recommendedClauses = response.recommended_clauses.filter((clause) => clause.clause_text.trim().length > 0);
  const hasClauses = recommendedClauses.length > 0;
  const intro = buildAssistantIntro(response);

  return (
    <>
      <p>{intro}</p>
      {response.cautions.length ? (
        <div className="chat-caution">
          {response.cautions.slice(0, 2).map((caution) => (
            <p key={caution}>{caution}</p>
          ))}
        </div>
      ) : null}
      {hasClauses ? (
        <div className="recommended-clauses">
          {recommendedClauses.slice(0, 3).map((clause) => (
            <details key={clause.title} className="recommended-clause">
              <summary>
                <strong>{clause.title}</strong>
                <span>{clause.why}</span>
              </summary>
              <p className="clause-text">{clause.clause_text}</p>
              {clause.negotiation_note ? <p className="detail-line">{clause.negotiation_note}</p> : null}
            </details>
          ))}
        </div>
      ) : null}
    </>
  );
}

function buildAssistantIntro(response: ContractChatResponse): string {
  const firstParagraph = response.answer.split("\n").find((item) => item.trim())?.trim() ?? response.answer;
  const sentences = firstParagraph
    .split(/(?<=[.!?。]|다\.|요\.)\s+/)
    .map((item) => item.trim())
    .filter(Boolean);
  const intro = sentences.slice(0, 2).join(" ");
  return intro || firstParagraph;
}
