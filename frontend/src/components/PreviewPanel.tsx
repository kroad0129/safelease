type PreviewPanelProps = {
  submitting: boolean;
  previewMode: "image" | "pdf";
  highlightedImageUrl: string | null;
  highlightedPdfUrl: string | null;
  onPreviewModeChange: (mode: "image" | "pdf") => void;
  onReset?: () => void;
};

export function PreviewPanel({
  submitting,
  previewMode,
  highlightedImageUrl,
  highlightedPdfUrl,
  onPreviewModeChange,
  onReset,
}: PreviewPanelProps) {
  return (
    <div className="preview-panel">
      <div className="panel-header">
        <div>
          <p className="panel-eyebrow">Document Preview</p>
        </div>
        <div className="preview-header-actions">
          {onReset ? (
            <button type="button" className="secondary-button preview-reset-button" onClick={onReset}>
              다른 계약서 업로드
            </button>
          ) : null}
          <div className="view-toggle">
            <button
              type="button"
              className={previewMode === "image" ? "toggle-button active" : "toggle-button"}
              onClick={() => onPreviewModeChange("image")}
              disabled={!highlightedImageUrl}
            >
              이미지
            </button>
            <button
              type="button"
              className={previewMode === "pdf" ? "toggle-button active" : "toggle-button"}
              onClick={() => onPreviewModeChange("pdf")}
              disabled={!highlightedPdfUrl}
            >
              PDF
            </button>
          </div>
        </div>
      </div>

      <div className="preview-frame">
        {submitting ? (
          <div className="loading-state">
            <p className="loading-title">계약서를 검토하고 있습니다.</p>
            <p className="loading-copy">분석이 끝나면 하이라이트와 검토 결과가 표시됩니다.</p>
          </div>
        ) : previewMode === "pdf" && highlightedPdfUrl ? (
          <iframe className="pdf-frame" src={highlightedPdfUrl} title="하이라이트 PDF 미리보기" />
        ) : highlightedImageUrl ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img className="preview-image" src={highlightedImageUrl} alt="하이라이트된 계약서 이미지" />
        ) : (
          <div className="empty-state">
            <p>표시할 하이라이트 미리보기 파일이 없습니다.</p>
          </div>
        )}
      </div>
    </div>
  );
}
