const WF_CHAT_COPY_LIMIT = 170;
const TRADEFRAME_SUFFIX = "via TradeFrame";

export type CopyOptions = {
  maxLength?: number;
  margin?: number;
};

export function copyText(text: string) {
  if (text) void navigator.clipboard?.writeText(text);
}

export function splitCopyText(text: string, limit = WF_CHAT_COPY_LIMIT): string[] {
  const source = text.trim();
  if (!source) return [];
  const suffixLength = TRADEFRAME_SUFFIX.length + 1;
  const contentLimit = Math.max(20, limit - suffixLength);
  if (source.length <= contentLimit) return [`${source} ${TRADEFRAME_SUFFIX}`];

  const separator = source.includes(", ") ? ", " : source.includes(" | ") ? " | " : "";
  const joiner = separator || " ";
  const parts = separator
    ? source.split(separator).map((part) => part.trim()).filter(Boolean)
    : source.split(/(?<=\])\s+(?=\[)/).map((part) => part.trim()).filter(Boolean);
  if (parts.length <= 1) return hardSplit(source, contentLimit).map((chunk) => `${chunk} ${TRADEFRAME_SUFFIX}`);

  const chunks: string[] = [];
  let current = "";
  for (const part of parts) {
    const candidate = current ? `${current}${joiner}${part}` : part;
    if (candidate.length <= contentLimit) {
      current = candidate;
      continue;
    }
    if (current) chunks.push(`${current} ${TRADEFRAME_SUFFIX}`);
    if (part.length <= contentLimit) {
      current = part;
    } else {
      chunks.push(...hardSplit(part, contentLimit).map((chunk) => `${chunk} ${TRADEFRAME_SUFFIX}`));
      current = "";
    }
  }
  if (current) chunks.push(`${current} ${TRADEFRAME_SUFFIX}`);
  return chunks;
}

function hardSplit(text: string, limit: number): string[] {
  const chunks: string[] = [];
  for (let index = 0; index < text.length; index += limit) {
    chunks.push(text.slice(index, index + limit));
  }
  return chunks;
}

export function CopyChunks({
  text,
  label = "Copy",
  options,
  className = "border border-cyan-500 px-3 py-2 text-sm font-semibold text-cyan-100 disabled:border-slate-700 disabled:text-slate-500",
  buttonClassName,
}: {
  text: string;
  label?: string;
  options?: CopyOptions;
  className?: string;
  buttonClassName?: string;
}) {
  const maxLength = Math.max(20, (options?.maxLength ?? WF_CHAT_COPY_LIMIT) - (options?.margin ?? 0));
  const chunks = splitCopyText(text, maxLength);
  const disabled = chunks.length === 0;
  if (chunks.length <= 1) {
    return (
      <button type="button" onClick={() => copyText(chunks[0] ?? "")} disabled={disabled} className={buttonClassName ?? className}>
        {label}
      </button>
    );
  }
  return (
    <div className="flex flex-wrap gap-2">
      {chunks.map((chunk, index) => (
        <button key={`${index}-${chunk.slice(0, 12)}`} type="button" onClick={() => copyText(chunk)} className={buttonClassName ?? className}>
          {label} {index + 1}
        </button>
      ))}
    </div>
  );
}
