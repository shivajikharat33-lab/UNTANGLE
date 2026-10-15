import { useEffect, useState, type FormEvent } from "react";
import { useNavigate } from "react-router";
import { getUploadLimit, uploadJob } from "../api/jobs";
import { ApiError } from "../api/client";
import { Alert } from "../components/Alert";
import { Button } from "../components/Button";
import { FileDropZone } from "../components/FileDropZone";
import { PageHeader } from "../components/PageHeader";
import { Spinner } from "../components/Spinner";

type Chosen = {
  file: File;
  message: string | null;
};

function extensionMessage(file: File, extension: string, label: string): string | null {
  if (!file.name.toLowerCase().endsWith(extension)) {
    return `Choose a ${extension} file for the ${label}.`;
  }
  if (file.size <= 0) {
    return "That file is empty.";
  }
  return null;
}

function sizeMessage(file: File, maxBytes: number, maxMb: number): string | null {
  if (file.size > maxBytes) {
    return `That file is larger than the ${maxMb} MB limit.`;
  }
  return null;
}

export function NewProjectPage() {
  const navigate = useNavigate();
  const [name, setName] = useState("");
  const [maxMb, setMaxMb] = useState<number | null>(null);
  const [limitError, setLimitError] = useState<ApiError | null>(null);
  const [pid, setPid] = useState<Chosen | null>(null);
  const [ioList, setIoList] = useState<Chosen | null>(null);
  const [uploadError, setUploadError] = useState<ApiError | null>(null);
  const [uploading, setUploading] = useState(false);
  const [loaded, setLoaded] = useState(0);
  const [total, setTotal] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    getUploadLimit(controller.signal)
      .then((config) => {
        setMaxMb(config.max_upload_mb);
        setLimitError(null);
      })
      .catch((caught: unknown) => {
        if (caught instanceof DOMException && caught.name === "AbortError") {
          return;
        }
        setLimitError(caught instanceof ApiError ? caught : new ApiError("The upload limit could not be loaded.", 0, null));
      });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    if (maxMb === null) {
      return;
    }
    const maxBytes = maxMb * 1024 * 1024;
    setPid((current) => (current ? { ...current, message: sizeMessage(current.file, maxBytes, maxMb) ?? current.message } : current));
    setIoList((current) => (current ? { ...current, message: sizeMessage(current.file, maxBytes, maxMb) ?? current.message } : current));
  }, [maxMb]);

  function choosePdf(file: File) {
    const message = extensionMessage(file, ".pdf", "P&ID") ?? (maxMb === null ? null : sizeMessage(file, maxMb * 1024 * 1024, maxMb));
    setPid({ file, message });
    setUploadError(null);
  }

  function chooseWorkbook(file: File) {
    const message = extensionMessage(file, ".xlsx", "IO list") ?? (maxMb === null ? null : sizeMessage(file, maxMb * 1024 * 1024, maxMb));
    setIoList({ file, message });
    setUploadError(null);
  }

  const ready = Boolean(pid && ioList && !pid.message && !ioList.message && maxMb !== null && !uploading);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!pid || !ioList || pid.message || ioList.message) {
      return;
    }
    setUploading(true);
    setUploadError(null);
    setLoaded(0);
    setTotal(0);
    try {
      const job = await uploadJob({ name, pid: pid.file, ioList: ioList.file }, (nextLoaded, nextTotal) => {
        setLoaded(nextLoaded);
        setTotal(nextTotal);
      });
      navigate(`/app/projects/${job.id}/processing`);
    } catch (caught) {
      setUploadError(caught instanceof ApiError ? caught : new ApiError("The upload failed.", 0, null));
      setUploading(false);
    }
  }

  const percent = total > 0 ? Math.round((loaded / total) * 100) : 0;

  return (
    <div className="mx-auto max-w-3xl">
      <PageHeader
        eyebrow="New project"
        title="Upload the drawing and the IO list"
        description="Both files are stored as they are. Intake reads the page count, the PDF type, and the Excel sheets. It does not match tags."
      />

      {limitError ? (
        <div className="mb-4">
          <Alert tone="error" title={limitError.message}>
            {limitError.body?.request_id ? <p>Request id: {limitError.body.request_id}</p> : null}
          </Alert>
        </div>
      ) : null}

      {maxMb === null && !limitError ? <Spinner label="Loading the upload limit" /> : null}

      <form className="space-y-4" onSubmit={submit}>
        <label className="block">
          <span className="text-sm font-semibold">Project name</span>
          <input
            value={name}
            onChange={(event) => setName(event.target.value)}
            disabled={uploading}
            className="mt-1 w-full rounded-control border border-line bg-paper-raised px-3 py-2 text-sm"
            placeholder="Optional. Leave blank for an untitled project."
          />
        </label>

        <FileDropZone
          label="P&ID PDF"
          hint={maxMb === null ? "A .pdf file." : `A .pdf file, up to ${maxMb} MB.`}
          accept=".pdf,application/pdf"
          file={pid?.file ?? null}
          message={pid?.message ?? null}
          disabled={uploading || maxMb === null}
          onSelect={choosePdf}
          onClear={() => setPid(null)}
        />
        <FileDropZone
          label="IO list"
          hint={maxMb === null ? "An .xlsx workbook." : `An .xlsx workbook, up to ${maxMb} MB.`}
          accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
          file={ioList?.file ?? null}
          message={ioList?.message ?? null}
          disabled={uploading || maxMb === null}
          onSelect={chooseWorkbook}
          onClear={() => setIoList(null)}
        />

        {uploading ? (
          <div>
            <p className="text-sm font-semibold">Uploading {percent}%</p>
            <div
              className="mt-2 h-2 overflow-hidden rounded-full bg-line"
              role="progressbar"
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={percent}
              aria-label="Upload progress"
            >
              <div className="h-full bg-teal" style={{ width: `${percent}%` }} />
            </div>
          </div>
        ) : null}

        {uploadError ? (
          <Alert tone="error" title={uploadError.message}>
            {uploadError.body?.request_id ? <p>Request id: {uploadError.body.request_id}</p> : null}
          </Alert>
        ) : null}

        <Button type="submit" disabled={!ready}>
          Create project
        </Button>
      </form>
    </div>
  );
}
