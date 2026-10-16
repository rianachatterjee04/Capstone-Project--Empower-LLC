"use client";
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch, apiPatch, apiPost, apiUpload } from "@/lib/api";
import { Button } from "@/components/Button";
import { Input } from "@/components/Input";
import { PageHeader, Surface, SectionTitle, Pill, EmptyState } from "@/components/ds";

// These two must match the server (hr_documents_service.py). A test compares them.
const ACCEPTED_EXTENSIONS = [".txt", ".md", ".pdf", ".docx"];
const MAX_FILE_BYTES = 5 * 1024 * 1024;

type KnowledgeDoc = {
  id: string;
  title: string;
  category: string;
  source: string;
  status: string;
  preview: string;
  chars: number;
  meta?: {
    filename?: string;
    kind?: string;
    size_bytes?: number;
    pages?: number | null;
    uploaded_at?: string;
  };
};

type Notice = { tone: "ok" | "error"; text: string };

function extensionOf(name: string): string {
  const dot = name.lastIndexOf(".");
  return dot === -1 ? "" : name.slice(dot).toLowerCase();
}

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${Math.round(n / 1024)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

/** Why this file cannot be uploaded, or null. The server checks again. */
function fileProblem(file: File): string | null {
  if (!ACCEPTED_EXTENSIONS.includes(extensionOf(file.name))) {
    return `That file type is not supported. Upload a ${ACCEPTED_EXTENSIONS.join(", ")} file.`;
  }
  if (file.size === 0) return "That file is empty.";
  if (file.size > MAX_FILE_BYTES) {
    return `That file is larger than ${MAX_FILE_BYTES / (1024 * 1024)} MB.`;
  }
  return null;
}

export default function HrKnowledgePage() {
  const qc = useQueryClient();
  const [file, setFile] = useState<File | null>(null);
  const [inputKey, setInputKey] = useState(0);
  const [title, setTitle] = useState("");
  const [category, setCategory] = useState("policy");
  const [uploading, setUploading] = useState(false);
  const [notice, setNotice] = useState<Notice | null>(null);

  const [editingId, setEditingId] = useState<string | null>(null);
  const [draftTitle, setDraftTitle] = useState("");
  const [draftCategory, setDraftCategory] = useState("");
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  const q = useQuery({
    queryKey: ["hr-knowledge-docs"],
    queryFn: () => apiFetch<{ items: KnowledgeDoc[] }>("/ai-helpdesk/documents"),
  });
  const docs = q.data?.items ?? [];
  const activeCount = docs.filter((d) => d.status === "active").length;

  const refresh = () => qc.invalidateQueries({ queryKey: ["hr-knowledge-docs"] });

  function chooseFile(next: File | null) {
    setNotice(null);
    if (next) {
      const problem = fileProblem(next);
      if (problem) {
        setFile(null);
        setInputKey((k) => k + 1);
        setNotice({ tone: "error", text: problem });
        return;
      }
    }
    setFile(next);
  }

  async function upload() {
    if (!file) return;
    setUploading(true);
    setNotice(null);
    try {
      const form = new FormData();
      form.append("file", file);
      if (title.trim()) form.append("title", title.trim());
      form.append("category", category.trim() || "policy");
      const out = await apiUpload<{ title: string; chars: number }>("/ai-helpdesk/documents/upload", form);
      setNotice({
        tone: "ok",
        text: `Uploaded "${out.title}". ${out.chars.toLocaleString()} characters of text can now be used by the AI helpdesk.`,
      });
      setFile(null);
      setTitle("");
      setInputKey((k) => k + 1);
      await refresh();
    } catch (e) {
      setNotice({ tone: "error", text: (e as Error).message });
    } finally {
      setUploading(false);
    }
  }

  async function run(id: string, action: () => Promise<unknown>, done: string) {
    setBusyId(id);
    setNotice(null);
    try {
      await action();
      setNotice({ tone: "ok", text: done });
      await refresh();
    } catch (e) {
      setNotice({ tone: "error", text: (e as Error).message });
    } finally {
      setBusyId(null);
    }
  }

  function startEdit(d: KnowledgeDoc) {
    setEditingId(d.id);
    setDraftTitle(d.title);
    setDraftCategory(d.category);
    setConfirmDeleteId(null);
  }

  async function saveEdit(id: string) {
    await run(
      id,
      () => apiPatch(`/ai-helpdesk/documents/${id}`, { title: draftTitle, category: draftCategory }),
      "Document updated.",
    );
    setEditingId(null);
  }

  return (
    <div className="space-y-7 fp-fade-in">
      <PageHeader
        eyebrow="AI & Automation"
        title="HR knowledge base"
        subtitle="Upload HR policies and guides so the AI helpdesk can answer from them. Text is read from PDF, Word, text and Markdown files."
      />

      <Surface className="space-y-1">
        <div className="text-sm text-body">
          Uploaded documents are kept in memory on the server for now, so they are cleared when the server restarts.
          The original file is not stored, only its text.
        </div>
      </Surface>

      <Surface className="space-y-3">
        <SectionTitle title="Upload a document" description="PDF, Word (.docx), text or Markdown, up to 5 MB." />
        <label className="block">
          <div className="mb-1 text-sm font-medium text-ink">File</div>
          <input
            key={inputKey}
            type="file"
            accept={ACCEPTED_EXTENSIONS.join(",")}
            onChange={(e) => chooseFile(e.target.files?.[0] ?? null)}
            className="block w-full text-sm text-body"
          />
        </label>
        {file ? (
          <div className="text-xs text-muted">
            {file.name}, {formatBytes(file.size)}
          </div>
        ) : null}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <Input
            label="Title (optional)"
            hint="Leave empty to use the file name."
            value={title}
            onChange={(e) => setTitle(e.target.value)}
          />
          <Input label="Category" value={category} onChange={(e) => setCategory(e.target.value)} />
        </div>
        <Button onClick={upload} disabled={!file || uploading}>
          {uploading ? "Uploading…" : "Upload document"}
        </Button>
        {notice ? (
          <div className={notice.tone === "error" ? "text-sm text-danger-fg" : "text-sm text-body"} role="status">
            {notice.text}
          </div>
        ) : null}
      </Surface>

      <Surface>
        <SectionTitle title="Documents" description={`${docs.length} total, ${activeCount} active`} />
        {q.isLoading ? <div className="mt-3 text-sm text-muted">Loading…</div> : null}
        {q.error ? <div className="mt-3 text-sm text-danger-fg">{(q.error as Error).message}</div> : null}
        {!q.isLoading && !q.error && docs.length === 0 ? (
          <EmptyState title="No documents yet" description="Upload a document above to add it to the knowledge base." />
        ) : (
          <div className="mt-4 space-y-3">
            {docs.map((d) => {
              const uploaded = d.source === "upload";
              const archived = d.status === "archived";
              const busy = busyId === d.id;
              return (
                <div
                  key={d.id}
                  className={"rounded-md border border-line bg-canvas p-3" + (archived ? " opacity-70" : "")}
                >
                  {editingId === d.id ? (
                    <div className="space-y-2">
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                        <Input label="Title" value={draftTitle} onChange={(e) => setDraftTitle(e.target.value)} />
                        <Input label="Category" value={draftCategory} onChange={(e) => setDraftCategory(e.target.value)} />
                      </div>
                      <div className="flex gap-2">
                        <Button onClick={() => saveEdit(d.id)} disabled={busy}>Save</Button>
                        <Button variant="secondary" onClick={() => setEditingId(null)} disabled={busy}>Cancel</Button>
                      </div>
                    </div>
                  ) : (
                    <>
                      <div className="flex flex-wrap items-center gap-2">
                        <div className="font-medium text-sm text-ink">{d.title}</div>
                        <Pill tone="neutral">{d.category}</Pill>
                        <Pill tone={archived ? "warn" : "success"}>{archived ? "Archived" : "Active"}</Pill>
                        <Pill tone="neutral">{uploaded ? "Uploaded" : "Built in"}</Pill>
                      </div>
                      {uploaded && d.meta ? (
                        <div className="mt-1 text-xs text-muted">
                          {[
                            d.meta.filename,
                            d.meta.size_bytes != null ? formatBytes(d.meta.size_bytes) : null,
                            d.meta.pages ? `${d.meta.pages} page${d.meta.pages === 1 ? "" : "s"}` : null,
                            `${d.chars.toLocaleString()} characters`,
                            d.meta.uploaded_at ? new Date(d.meta.uploaded_at).toLocaleString() : null,
                          ]
                            .filter(Boolean)
                            .join(", ")}
                        </div>
                      ) : null}
                      <div className="mt-2 text-sm text-body">{d.preview}</div>
                      <div className="mt-3 flex flex-wrap gap-2">
                        {uploaded ? (
                          <Button variant="secondary" onClick={() => startEdit(d)} disabled={busy}>Edit</Button>
                        ) : null}
                        {archived ? (
                          <Button
                            variant="secondary"
                            disabled={busy}
                            onClick={() => run(d.id, () => apiPost(`/ai-helpdesk/documents/${d.id}/restore`, {}), "Document restored.")}
                          >
                            Restore
                          </Button>
                        ) : (
                          <Button
                            variant="secondary"
                            disabled={busy}
                            onClick={() => run(d.id, () => apiPost(`/ai-helpdesk/documents/${d.id}/archive`, {}), "Document archived. The helpdesk will no longer use it.")}
                          >
                            Archive
                          </Button>
                        )}
                        {uploaded && confirmDeleteId !== d.id ? (
                          <Button variant="danger" disabled={busy} onClick={() => setConfirmDeleteId(d.id)}>Delete</Button>
                        ) : null}
                        {uploaded && confirmDeleteId === d.id ? (
                          <>
                            <Button
                              variant="danger"
                              disabled={busy}
                              onClick={async () => {
                                await run(d.id, () => apiFetch(`/ai-helpdesk/documents/${d.id}`, { method: "DELETE" }), "Document deleted.");
                                setConfirmDeleteId(null);
                              }}
                            >
                              Confirm delete
                            </Button>
                            <Button variant="secondary" onClick={() => setConfirmDeleteId(null)} disabled={busy}>Cancel</Button>
                          </>
                        ) : null}
                      </div>
                    </>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </Surface>
    </div>
  );
}
