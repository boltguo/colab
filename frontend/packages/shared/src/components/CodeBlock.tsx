import React, { useEffect, useState } from "react";
import type { ThemedToken } from "shiki/core";
import { CheckCircleFilled, CopyOutlined, IconButton, ScrollArea, Tooltip, useStudioFeedback } from "../ui/primitives";

export interface CodeBlockProps {
  code: string;
  language?: string;
  title?: string;
  onCopy?: (code: string) => Promise<void>;
}

export function CodeBlock({ code, language = "text", title, onCopy }: CodeBlockProps) {
  const { message } = useStudioFeedback();
  const [highlighted, setHighlighted] = useState<{ code: string; language: string; tokens: ThemedToken[][] } | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    let cancelled = false;
    // Debounce streaming replies and discard results for outdated code.
    const timer = window.setTimeout(() => {
      void import("../utils/highlightCode").then(({ highlightCode }) => highlightCode(code, language))
        .then((tokens) => { if (!cancelled && tokens) setHighlighted({ code, language, tokens }); })
        .catch((error) => { console.warn("Syntax highlighting unavailable; using plain text.", error); });
    }, 80);
    return () => { cancelled = true; window.clearTimeout(timer); };
  }, [code, language]);

  useEffect(() => {
    if (!copied) return;
    const timer = window.setTimeout(() => setCopied(false), 1600);
    return () => window.clearTimeout(timer);
  }, [copied]);

  const copy = async () => {
    try {
      if (onCopy) await onCopy(code);
      else await navigator.clipboard.writeText(code);
      setCopied(true);
    } catch {
      message.warning("复制失败，请手动选中代码复制");
    }
  };
  const tokens = highlighted?.code === code && highlighted.language === language ? highlighted.tokens : null;
  return <div className="studio-syntax-block">
    <div className="studio-syntax-header">
      <span>{title || language}</span>
      <Tooltip title={copied ? "已复制" : "复制代码"}>
        <IconButton type="button" variant="standard" size="xs" aria-label={copied ? "已复制代码" : "复制代码"}
          icon={copied ? <CheckCircleFilled /> : <CopyOutlined />} onClick={() => void copy()} />
      </Tooltip>
    </div>
    <ScrollArea className="studio-code-scroll" maxHeight="var(--studio-code-max-height, 420px)">
    <pre className="studio-syntax-pre"><code>{tokens ? tokens.map((line, index) => <React.Fragment key={index}>
      {line.map((token, tokenIndex) => <span key={tokenIndex} style={{ color: token.color }}>{token.content}</span>)}
      {index < tokens.length - 1 ? "\n" : null}
    </React.Fragment>) : code}</code></pre>
    </ScrollArea>
  </div>;
}
