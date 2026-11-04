import { useId, useRef, useState, type DragEvent, type KeyboardEvent, type ReactNode } from "react";
import { X } from "lucide-react";

interface Props {
  label: string;
  hint: string;
  /** Allowed extensions, lower-case with a dot, e.g. [".pdf", ".txt"]. */
  accept: string[];
  multiple?: boolean;
  files: File[];
  onChange: (files: File[]) => void;
  icon: ReactNode;
  disabled?: boolean;
}

export function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/**
 * Drag-and-drop or click-to-browse upload area.
 * Files with the wrong extension are rejected here, shown as a red chip, and never added.
 */
export function UploadZone({ label, hint, accept, multiple = false, files, onChange, icon, disabled }: Props) {
  const id = useId();
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [rejected, setRejected] = useState<string[]>([]);
  const kinds = accept.map((ext) => ext.slice(1).toUpperCase()).join("/");

  const accepts = (file: File) => accept.some((ext) => file.name.toLowerCase().endsWith(ext));

  function add(list: FileList | null) {
    if (!list || disabled) return;
    const incoming = Array.from(list);
    const ok = incoming.filter(accepts);
    setRejected(incoming.filter((f) => !accepts(f)).map((f) => `${f.name} – not a ${kinds} file`));
    if (ok.length === 0) return;
    if (!multiple) {
      onChange([ok[0]]);
      return;
    }
    // Re-adding a file with the same name replaces it instead of duplicating it.
    const byName = new Map(files.map((f) => [f.name, f]));
    ok.forEach((f) => byName.set(f.name, f));
    onChange([...byName.values()].sort((a, b) => a.name.localeCompare(b.name)));
  }

  const open = () => !disabled && inputRef.current?.click();
  const onKeyDown = (e: KeyboardEvent) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      open();
    }
  };
  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setDragging(false);
    add(e.dataTransfer.files);
  };

  return (
    <div className="upload">
      <div className="upload__label" id={`${id}-label`}>
        <span>{label}</span>
        {files.length > 0 && <span className="upload__count">{multiple ? `${files.length} file(s)` : "ready"}</span>}
      </div>

      <div
        role="button"
        tabIndex={disabled ? -1 : 0}
        aria-labelledby={`${id}-label`}
        aria-describedby={`${id}-hint`}
        aria-disabled={disabled}
        className={`dropzone${dragging ? " is-dragging" : ""}${files.length ? " is-filled" : ""}`}
        onClick={open}
        onKeyDown={onKeyDown}
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
      >
        {icon}
        <span>
          Drop {multiple ? "files" : "a file"} here or <span className="dropzone__browse">browse</span>
        </span>
        <span className="dropzone__hint" id={`${id}-hint`}>
          {hint}
        </span>
      </div>
      <input
        ref={inputRef}
        type="file"
        hidden
        accept={accept.join(",")}
        multiple={multiple}
        onChange={(e) => {
          add(e.target.files);
          e.target.value = ""; // allow picking the same file again
        }}
      />

      {rejected.length > 0 && (
        <ul className="chips" role="alert">
          {rejected.map((msg) => (
            <li key={msg} className="chip chip--error">
              <span className="chip__name">{msg}</span>
            </li>
          ))}
        </ul>
      )}

      {files.length > 0 && (
        <>
          <ul className="chips" aria-label={`${label} selected`}>
            {files.map((f) => (
              <li key={f.name} className="chip" title={f.name}>
                <span className="chip__name">{f.name}</span>
                <span className="chip__size">{formatSize(f.size)}</span>
                <button
                  type="button"
                  className="icon-btn"
                  aria-label={`Remove ${f.name}`}
                  disabled={disabled}
                  onClick={() => onChange(files.filter((x) => x !== f))}
                >
                  <X size={13} />
                </button>
              </li>
            ))}
          </ul>
          {multiple && files.length > 1 && (
            <button type="button" className="text-btn" disabled={disabled} onClick={() => onChange([])}>
              Clear all
            </button>
          )}
        </>
      )}
    </div>
  );
}
