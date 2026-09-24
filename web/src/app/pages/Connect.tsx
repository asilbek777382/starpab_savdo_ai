import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { del, get, post } from "../api";
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

function InstagramCard({ ch }: { ch: Channels }) {
  const { t, date } = useI18n();
  const qc = useQueryClient();
  const connect = useMutation({
    mutationFn: () => post<{ url: string }>("/api/instagram/connect"),
    onSuccess: (r) => {
      window.location.href = r.url;
    },
  });
  const disconnect = useMutation({
    mutationFn: () => del("/api/instagram"),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["channels"] }),
  });
  const ig = ch.instagram;
  return (
    <Card title={t("connect.instagram")} actions={ig && <Badge tone="green">✓ {t("connect.ig_connected", { name: ig.display_name ?? "Instagram" })}</Badge>}>
      <p className="text-sm text-slate-600">{t("connect.ig_hint")}</p>
      <ErrorBox error={connect.error ?? disconnect.error} />
      {ig ? (
        <div className="mt-4 flex flex-wrap items-center gap-3">
          {ig.token_expires_at && <span className="text-sm text-slate-500">{t("connect.ig_expires", { date: date(ig.token_expires_at, false) })}</span>}
          <Button size="sm" variant="danger" onClick={() => disconnect.mutate()} loading={disconnect.isPending}>
            {t("connect.ig_disconnect")}
          </Button>
        </div>
      ) : !ch.instagram_configured ? (
        <p className="mt-3 text-sm text-amber-800">{t("connect.ig_not_configured")}</p>
      ) : !ch.instagram_allowed ? (
        <p className="mt-3 text-sm text-amber-800">{t("connect.ig_plan")}</p>
      ) : (
        <div className="mt-4 space-y-3">
          <p className="rounded-lg bg-slate-50 px-3 py-2.5 text-xs leading-relaxed text-slate-600">{t("connect.ig_steps")}</p>
          <button
            type="button"
            onClick={() => connect.mutate()}
            disabled={connect.isPending}
            className="inline-flex items-center gap-2 rounded-lg bg-gradient-to-r from-[#833AB4] via-[#E1306C] to-[#F77737] px-4 py-2.5 text-sm font-semibold text-white shadow-sm hover:opacity-90 disabled:opacity-60"
          >
            📸 {t("connect.ig_btn")}
          </button>
        </div>
      )}
      <p className="mt-4 text-xs text-slate-500">{t("connect.ig_window")}</p>
    </Card>
  );
}

const IG_RESULT = { ok: "connect.ig_ok", error: "connect.ig_error", taken: "connect.ig_taken" } as const;

export function ConnectPage() {
  const { t } = useI18n();
  const [params] = useSearchParams();
  const igResult = params.get("instagram") as keyof typeof IG_RESULT | null;
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
      {igResult && IG_RESULT[igResult] && (
        <div
          role="status"
          className={
            igResult === "ok"
              ? "mb-6 rounded-xl bg-emerald-50 px-4 py-3 text-sm font-medium text-emerald-800 ring-1 ring-emerald-200"
              : "mb-6 rounded-xl bg-red-50 px-4 py-3 text-sm font-medium text-red-800 ring-1 ring-red-200"
          }
        >
          {t(IG_RESULT[igResult])}
        </div>
      )}
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
        {ch && <InstagramCard ch={ch} />}
      </div>
    </>
  );
}
