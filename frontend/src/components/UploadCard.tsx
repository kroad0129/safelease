import type { ChangeEvent, FormEvent } from "react";
import { useState } from "react";

type UploadCardProps = {
  selectedFile: File | null;
  submitting: boolean;
  errorMessage: string | null;
  onFileChange: (event: ChangeEvent<HTMLInputElement>) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
};

export function UploadCard({
  selectedFile,
  submitting,
  errorMessage,
  onFileChange,
  onSubmit,
}: UploadCardProps) {
  const [uploadAuthorityChecked, setUploadAuthorityChecked] = useState(false);
  const [thirdPartyChecked, setThirdPartyChecked] = useState(false);
  const canSubmit = Boolean(selectedFile) && uploadAuthorityChecked && thirdPartyChecked && !submitting;

  return (
    <section className="upload-hero" aria-labelledby="upload-title">
      <div className="upload-intro">
        <p className="upload-kicker">SafeLease</p>
        <h1 id="upload-title">세이프리스</h1>
        <p>
          안녕하세요, 세리예요. 저한테 검토할 서류를 보여주면 계약 조건, 검증 결과,
          불리할 수 있는 조항을 쉽게 정리해드릴게요.
        </p>
        <div className="upload-guide-notes" aria-label="서비스 이용 안내">
          <p>세리의 검토 결과는 참고용이며, 중요한 결정 전에는 전문가 확인이 필요할 수 있어요.</p>
          <p>
            업로드된 원본 PDF는 계약서 검토를 위해 일시적으로만 사용됩니다.
          </p>
          <p>검토가 완료되면 원본 파일과 개인정보는 저장하지 않고 삭제되며, 특약사항·계약조건 등 개인정보가
            제거된 분석 정보는 계약 검토 기능 개선 및 분석 결과 제공을 위해 저장될 수 있습니다.
          </p>
        </div>
      </div>

      <form className="upload-card" onSubmit={onSubmit}>
        <div className="upload-dropzone">
          <label className="upload-label" htmlFor="pdf-upload">
            PDF 파일 선택
          </label>
          <input id="pdf-upload" type="file" accept="application/pdf" onChange={onFileChange} />
        </div>

        <p className="upload-help">검토까지 보통 1~2분 정도 소요돼요.</p>

        <div className="upload-consent-list" aria-label="검토 전 확인">
          <label className="upload-consent-item">
            <input
              type="checkbox"
              checked={uploadAuthorityChecked}
              onChange={(event) => setUploadAuthorityChecked(event.target.checked)}
            />
            <span>본인이 계약 당사자이거나, 해당 서류를 업로드·검토할 권한이 있음을 확인합니다.</span>
          </label>
          <label className="upload-consent-item">
            <input
              type="checkbox"
              checked={thirdPartyChecked}
              onChange={(event) => setThirdPartyChecked(event.target.checked)}
            />
            <span>서류에 제3자 정보가 포함될 수 있으며, 이를 계약 검토 목적으로 처리하는 데 필요한 권한이 있음을 확인합니다.</span>
          </label>
        </div>

        <button className="primary-button" type="submit" disabled={!canSubmit}>
          {submitting ? "검토 중..." : "검토 시작"}
        </button>
        {errorMessage ? <p className="error-text">{errorMessage}</p> : null}
      </form>
    </section>
  );
}
