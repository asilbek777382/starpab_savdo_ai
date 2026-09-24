import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import { get, post } from "../api";
import { useI18n } from "../i18n";
import type { ChatMessage, Conversation } from "../types";
import { Badge, Button, Card, cx, Empty, ErrorBox, Loading, PageHeader } from "../ui";

const CHANNEL_LABEL: Record<string, string> = {
  tg_business: "Telegram",
  tg_bot: "Telegram bot",
  instagram: "Instagram",
  test: "Test",
};

function StatusBadge({ c }: { c: Conversation }) {
  const { t, date } = useI18n();
  return c.status === "ai" ? (
    <Badge tone="brand">🤖 {t("conv.ai_on")}</Badge>
  ) : (
    <Badge tone="gold">
      🙋 {t("conv.ai_off")}
      {c.human_until && ` · ${t("conv.until", { time: date(c.human_until) })}`}
    </Badge>
  );
}

function Thread({ conv }: { conv: Conversation }) {
  const { t, date } = useI18n();
  const qc = useQueryClient();
  const msgs = useQuery({
    queryKey: ["messages", conv.id],
    queryFn: () => get<ChatMessage[]>(`/api/conversations/${conv.id}/messages`),
    refetchInterval: 10_000,
  });
  const toggle = useMutation({
    mutationFn: (enabled: boolean) => post(`/api/conversations/${conv.id}/ai`, { enabled }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["conversations"] }),
  });
  return (
    <Card
      title={conv.customer_name || `#${conv.customer_id}`}
      actions={
        conv.status === "ai" ? (
          <Button size="sm" variant="secondary" onClick={() => toggle.mutate(false)} loading={toggle.isPending}>
            {t("conv.stop_ai")}
          </Button>
        ) : (
          <Button size="sm" onClick={() => toggle.mutate(true)} loading={toggle.isPending}>
            {t("conv.start_ai")}
          </Button>
        )
      }
    >
      <div className="mb-3 flex flex-wrap items-center gap-2 text-xs text-slate-500">
        <StatusBadge c={conv} />
        <span>
          {t("conv.stage")}: {conv.stage}
        </span>
      </div>
      <ErrorBox error={toggle.error ?? msgs.error} />
      <div className="max-h-[60vh] space-y-2 overflow-y-auto rounded-xl bg-[#E7F3EF] p-3">
        {msgs.isLoading && <Loading />}
        {msgs.data?.map((m) => (
          <div key={m.id} className={cx("flex", m.role === "customer" ? "justify-start" : "justify-end")}>
            <div
              className={cx(
                "max-w-[85%] rounded-2xl px-3 py-2 text-sm shadow-sm",
                m.role === "customer" ? "rounded-bl-md bg-white" : m.role === "ai" ? "rounded-br-md bg-brand-50 ring-1 ring-brand-100" : "rounded-br-md bg-[#D9FDD3]",
              )}
            >
              <p className="mb-0.5 text-[11px] font-semibold text-slate-500">
                {t(`conv.role.${m.role}`)} · {date(m.created_at)}
              </p>
              <p className="whitespace-pre-line text-slate-800">{m.content}</p>
            </div>
          </div>
        ))}
      </div>
    </Card>
  );
}

export function ConversationsPage() {
  const { t, date } = useI18n();
  const [params, setParams] = useSearchParams();
  const convs = useQuery({
    queryKey: ["conversations"],
    queryFn: () => get<Conversation[]>("/api/conversations?limit=100"),
    refetchInterval: 15_000,
  });
  const selectedId = Number(params.get("c")) || null;
  const selected = convs.data?.find((c) => c.id === selectedId) ?? null;
  return (
    <>
      <PageHeader title={t("conv.title")} />
      <ErrorBox error={convs.error} />
      {convs.isLoading ? (
        <Loading />
      ) : !convs.data?.length ? (
        <Empty />
      ) : (
        <div className="grid gap-4 lg:grid-cols-[20rem_1fr]">
          <div className={cx("space-y-2", selected && "hidden lg:block")}>
            {convs.data.map((c) => (
              <button
                key={c.id}
                onClick={() => setParams({ c: String(c.id) })}
                className={cx(
                  "w-full rounded-xl bg-white p-3 text-left shadow-sm ring-1 transition",
                  c.id === selectedId ? "ring-brand-500" : "ring-slate-100 hover:ring-slate-300",
                )}
              >
                <p className="flex items-center justify-between gap-2 font-medium text-slate-900">
                  <span className="truncate">{c.customer_name || `#${c.customer_id}`}</span>
                  <span className="shrink-0 text-xs font-normal text-slate-400">{CHANNEL_LABEL[c.channel_type ?? ""] ?? ""}</span>
                </p>
                <div className="mt-1 flex items-center justify-between gap-2">
                  <StatusBadge c={c} />
                  {c.last_message_at && <span className="text-xs text-slate-400">{date(c.last_message_at)}</span>}
                </div>
              </button>
            ))}
          </div>
          <div>
            {selected ? (
              <>
                <button onClick={() => setParams({})} className="mb-3 text-sm font-medium text-brand-700 lg:hidden">
                  ← {t("common.back")}
                </button>
                <Thread key={selected.id} conv={selected} />
              </>
            ) : (
              <div className="hidden lg:block">
                <Empty>{t("conv.select")}</Empty>
              </div>
            )}
          </div>
        </div>
      )}
    </>
  );
}
