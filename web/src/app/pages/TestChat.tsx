import { useMutation } from "@tanstack/react-query";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { post } from "../api";
import { useI18n } from "../i18n";
import type { TestChatResult } from "../types";
import { Button, Card, cx, ErrorBox, PageHeader } from "../ui";
import { testedKey } from "./Dashboard";

type Line = { from: "me" | "ai" | "photo" | "note" | "voice"; text: string; audio?: string };

export function TestChatPage() {
  const { t } = useI18n();
  const [lines, setLines] = useState<Line[]>([]);
  const [text, setText] = useState("");
  const [asVoice, setAsVoice] = useState(false);
  const [tools, setTools] = useState<TestChatResult["tools"]>([]);
  const resetNext = useRef(false);
  const endRef = useRef<HTMLDivElement>(null);
  useEffect(() => endRef.current?.scrollIntoView({ block: "end" }), [lines]);

  const send = useMutation({
    mutationFn: (message: string) => post<TestChatResult>("/api/test-chat", { message, reset: resetNext.current, as_voice: asVoice }),
    onSuccess: (r) => {
      resetNext.current = false;
      try {
        localStorage.setItem(testedKey(), "1");
      } catch {
        /* e'tiborsiz */
      }
      const out: Line[] = r.replies.map((x) =>
        x.type === "photos"
          ? { from: "photo", text: `🖼 ${x.photos?.length ?? 0} × ${x.caption ?? ""}` }
          : x.type === "voice"
            ? { from: "voice", text: t("test.voice_reply"), audio: `data:${x.mime ?? "audio/ogg"};base64,${x.audio_b64}` }
            : { from: "ai", text: x.text ?? "" },
      );
      if (r.status === "ai_off") out.push({ from: "note", text: t("test.ai_off") });
      if (r.order_number) out.push({ from: "note", text: t("test.order", { n: r.order_number }) });
      if (r.lead_id) out.push({ from: "note", text: t("test.lead") });
      if (r.handed_off) out.push({ from: "note", text: t("test.handoff") });
      setLines((l) => [...l, ...out]);
      setTools(r.tools);
    },
  });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    const msg = text.trim();
    if (!msg) return;
    setLines((l) => [...l, { from: "me", text: asVoice ? `🎤 ${msg}` : msg }]);
    setText("");
    send.mutate(msg);
  };
  const reset = () => {
    resetNext.current = true;
    setLines([]);
    setTools([]);
  };
  return (
    <>
      <PageHeader
        title={t("test.title")}
        subtitle={t("test.subtitle")}
        actions={
          <Button variant="secondary" onClick={reset}>
            ↺ {t("test.reset")}
          </Button>
        }
      />
      <div className="grid gap-6 lg:grid-cols-[1fr_20rem]">
        <Card flush className="flex flex-col">
          <div className="h-[60vh] space-y-2 overflow-y-auto rounded-t-2xl bg-[#E7F3EF] p-4">
            {lines.map((l, i) => (
              <div key={i} className={cx("flex", l.from === "me" ? "justify-end" : l.from === "note" ? "justify-center" : "justify-start")}>
                <div
                  className={cx(
                    "max-w-[85%] whitespace-pre-line rounded-2xl px-3 py-2 text-sm shadow-sm",
                    l.from === "me" && "rounded-br-md bg-[#D9FDD3]",
                    l.from === "ai" && "rounded-bl-md bg-white",
                    l.from === "photo" && "rounded-bl-md bg-white text-slate-500",
                    l.from === "note" && "bg-brand-700 text-xs font-medium text-white",
                    l.from === "voice" && "rounded-bl-md bg-white",
                  )}
                >
                  {l.audio ? (
                    <span className="flex flex-col gap-1">
                      <span className="text-xs font-medium text-slate-500">🔊 {l.text}</span>
                      <audio controls src={l.audio} className="h-9 w-64 max-w-full" />
                    </span>
                  ) : (
                    l.text
                  )}
                </div>
              </div>
            ))}
            {send.isPending && (
              <div className="typing flex w-14 gap-1 rounded-2xl rounded-bl-md bg-white px-3 py-3 shadow-sm">
                <span className="h-1.5 w-1.5 rounded-full bg-slate-400" />
                <span className="h-1.5 w-1.5 rounded-full bg-slate-400" />
                <span className="h-1.5 w-1.5 rounded-full bg-slate-400" />
              </div>
            )}
            <div ref={endRef} />
          </div>
          <form onSubmit={submit} className="flex gap-2 border-t border-slate-100 p-3">
            <input
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder={t("test.placeholder")}
              aria-label={t("test.placeholder")}
              className="flex-1 rounded-lg border-0 px-3 py-2.5 text-sm ring-1 ring-slate-200 focus:ring-2 focus:ring-brand-500 focus:outline-none"
            />
            <Button type="submit" loading={send.isPending}>
              {t("test.send")}
            </Button>
          </form>
          <label className="flex items-center gap-2 px-3 pb-3 text-sm text-slate-600">
            <input type="checkbox" checked={asVoice} onChange={(e) => setAsVoice(e.target.checked)} className="h-4 w-4 accent-brand-700" />
            🎤 {t("test.as_voice")}
          </label>
          <div className="px-3 pb-3">
            <ErrorBox error={send.error} />
          </div>
        </Card>
        <Card title={t("test.tools")}>
          {tools.length ? (
            <ol className="space-y-3 text-xs">
              {tools.map((tool, i) => (
                <li key={i}>
                  <p className="font-mono font-semibold text-brand-700">{tool.tool}</p>
                  <pre className="mt-1 max-h-40 overflow-auto rounded-lg bg-slate-50 p-2 text-[11px] leading-snug text-slate-600">
                    {JSON.stringify(tool.input, null, 1)}
                  </pre>
                </li>
              ))}
            </ol>
          ) : (
            <p className="text-sm text-slate-400">—</p>
          )}
        </Card>
      </div>
    </>
  );
}
