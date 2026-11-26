import { useEffect, useRef } from "react";
import { useAuth } from "../../app/providers/AuthProvider";
import type { AddFileDefsStagedBlobRef, ListFilesView } from "../generated/artifacts";
import { keys } from "../keys";
import { api, segment, useCursor, useRead, withParams } from "./workspace";

export function useFiles(workspaceId: string, projectId: string | null, state: string, origin: string) {
  const cursor = useCursor(withParams("/files", { workspace_id: workspaceId, project_id: projectId, state, origin }));
  const scoped = keys.forScope({ workspaceId, projectId });
  const key = projectId === null ? [...keys.workspace(workspaceId), "files"] : scoped.files(projectId);
  const query = useRead<ListFilesView>(key, cursor.path);
  return { query, cursor };
}

async function sha256(file: Blob) {
  const bytes = typeof file.arrayBuffer === "function" ? await file.arrayBuffer() : await new Promise<ArrayBuffer>((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result as ArrayBuffer);
    reader.onerror = () => reject(reader.error);
    reader.readAsArrayBuffer(file);
  });
  const digest = new Uint8Array(await crypto.subtle.digest("SHA-256", bytes));
  return "sha256:" + Array.from(digest, byte => byte.toString(16).padStart(2, "0")).join("");
}

export function useBlobTransport() {
  const { transport } = useAuth();
  const lifetime = useRef<AbortController | null>(null);
  const cachedContent = useRef<{ id: string; etag: string; blob: Blob } | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    lifetime.current = controller;
    return () => {
      controller.abort();
      cachedContent.current = null;
    };
  }, [transport]);
  function sessionSignal() {
    const signal = lifetime.current?.signal;
    if (!signal) throw new Error("Сеанс не готов");
    signal.throwIfAborted();
    return signal;
  }
  return {
    sessionSignal,
    async stage(workspaceId: string, file: File, idempotencyKey: string): Promise<AddFileDefsStagedBlobRef> {
      const signal = sessionSignal();
      const expectedDigest = await sha256(file);
      signal.throwIfAborted();
      const path = withParams(`${api}/workspaces/${segment(workspaceId)}/blobs`, { media_type: file.type || "application/octet-stream" });
      const { data } = await transport.request<AddFileDefsStagedBlobRef>("POST", path, {
        // The browser derives Content-Length from the Blob.
        raw: file, contentType: "application/octet-stream", expectedDigest, idempotencyKey, signal,
      });
      signal.throwIfAborted();
      return data;
    },
    async content(id: string): Promise<Blob> {
      const signal = sessionSignal();
      const cached = cachedContent.current?.id === id ? cachedContent.current : null;
      const { data, etag, notModified } = await transport.request<Blob | undefined>(
        "GET", `${api}/file-versions/${segment(id)}/content`, {
          responseType: "blob", signal, ...(cached && { ifNoneMatch: cached.etag }),
        },
      );
      signal.throwIfAborted();
      if (notModified && cached) return cached.blob;
      if (data === undefined) throw new Error("Сервер не вернул содержимое версии");
      cachedContent.current = etag ? { id, etag, blob: data } : null;
      return data;
    },
  };
}

export function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  try {
    anchor.href = url;
    anchor.download = filename;
    document.body.append(anchor);
    anchor.click();
  } finally {
    anchor.remove();
    setTimeout(() => URL.revokeObjectURL(url), 0);
  }
}
