import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { get, post } from "../api";
import { useMe } from "../auth";
import { useI18n } from "../i18n";
import type { Channels } from "../types";
import { Badge, Button, Card, ErrorBox, PageHeader } from "../ui";

export function CopyButton({ text }: { text: string }) {
  const { t } = useI18n();
  const [copied, setCopied] = useState(false);
  return (
    <Button
      type="button"
      size="sm"
      variant="secondary"
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(text);
          setCopied(true);
          setTimeout(() => setCopied(false), 1800);
        } catch {
          /* clipboard yopiq bo'lishi mumkin */
        }
      }}
    >
      {copied ? t("common.copied") : t("common.copy")}
    </Button>
  );
}

export function ConnectPage() {
  const { t } = useI18n();
  const qc = useQueryClient();
  const { data: me } = useMe();
  const channels = useQuery({ queryKey: ["channels"], queryFn: () => get<Channels>("/api/channels") });
  const link = useMutation({ mutationFn: () => post<{ url: string }>("/api/auth/telegram-link") });
  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["me"] });
    qc.invalidateQueries({ queryKey: ["channels"] });
  };
  const ch = channels.data;
  return (
    <>
      <PageHeader
        title={t("connect.title")}
        actions={
          <Button variant="secondary" onClick={refresh}>
            ↻ {t("connect.refresh")}
          </Button>
        }
      />
      <ErrorBox error={channels.error ?? link.error} />
      <div className="space-y-6">
        <Card title={t("connect.account")} actions={me?.telegram_linked && <Badge tone="green">✓ {t("connect.linked")}</Badge>}>
          <p className="text-sm text-slate-600">{t("connect.account_hint")}</p>
          {!me?.telegram_linked && (
            <div className="mt-4 space-y-3">
              {link.data ? (
                <>
                  <a href={link.data.url} target="_blank" rel="noreferrer" className="inline-flex rounded-lg bg-[#229ED9] px-4 py-2.5 text-sm font-semibold text-white hover:opacity-90">
                    ✈ {t("common.open")} Telegram
                  </a>
                  <p className="text-sm text-slate-500">{t("connect.link_wait")}</p>
                </>
              ) : (
                <Button onClick={() => link.mutate()} loading={link.isPending}>
                  {t("connect.link_btn")}
                </Button>
              )}
            </div>
          )}
        </Card>
        <Card
          title={t("connect.business")}
          actions={ch && (ch.business_connected ? <Badge tone="green">✓ {t("connect.business_ok")}</Badge> : <Badge tone="gold">{t("connect.business_no")}</Badge>)}
        >
          <p className="text-sm leading-relaxed text-slate-600">{t("connect.business_steps", { bot: ch?.bot_username || "bot" })}</p>
        </Card>
        <Card title={t("connect.bot")}>
          <p className="mb-3 text-sm text-slate-600">{t("connect.bot_hint")}</p>
          {ch && (
            <div className="flex flex-wrap items-center gap-2">
              <code className="rounded-lg bg-slate-50 px-3 py-2 text-sm text-brand-900 ring-1 ring-slate-200">{ch.bot_link}</code>
              <CopyButton text={ch.bot_link} />
            </div>
          )}
        </Card>
      </div>
    </>
  );
}
