import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { get, getShopId } from "../api";
import { useCurrentShop, useMe } from "../auth";
import { DailyBars } from "../DailyBars";
import { useI18n } from "../i18n";
import type { MessageKey } from "../locales";
import type { Channels, DailyPoint, Product, Settings, Shop, Stats } from "../types";
import { Button, Card, cx, ErrorBox, Loading, PageHeader } from "../ui";

function Tile({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="rounded-2xl bg-white p-5 shadow-sm ring-1 ring-slate-100">
      <p className="text-sm text-slate-500">{label}</p>
      <p className="mt-2 text-2xl font-bold text-slate-900">{value}</p>
      {sub && <p className="mt-1 text-xs text-slate-500">{sub}</p>}
    </div>
  );
}

export function testedKey() {
  return `nv_tested_${getShopId()}`;
}

function SetupChecklist() {
  const { t } = useI18n();
  const { data: me } = useMe();
  const products = useQuery({ queryKey: ["products", "count"], queryFn: () => get<Product[]>("/api/products?limit=1") });
  const settings = useQuery({ queryKey: ["settings"], queryFn: () => get<Settings>("/api/settings") });
  const channels = useQuery({ queryKey: ["channels"], queryFn: () => get<Channels>("/api/channels") });
  let tested = false;
  try {
    tested = localStorage.getItem(testedKey()) === "1";
  } catch {
    /* e'tiborsiz */
  }
  const s = settings.data;
  const steps: { key: MessageKey; done: boolean; to: string }[] = [
    { key: "dash.step.catalog", done: (products.data?.length ?? 0) > 0, to: "/catalog" },
    { key: "dash.step.info", done: !!s && !!s.address && (s.delivery_zones.length > 0 || !!s.payment_methods), to: "/shop" },
    { key: "dash.step.test", done: tested, to: "/test" },
    { key: "dash.step.telegram", done: !!me?.telegram_linked, to: "/connect" },
    { key: "dash.step.business", done: !!channels.data?.business_connected, to: "/connect" },
  ];
  const done = steps.filter((x) => x.done).length;
  if (done === steps.length || products.isLoading || settings.isLoading) return null;
  return (
    <Card title={t("dash.setup")} actions={<span className="text-sm text-slate-500">{t("dash.setup_done", { done, total: steps.length })}</span>} className="mb-6">
      <div className="mb-4 h-2 overflow-hidden rounded-full bg-slate-100">
        <div className="h-full rounded-full bg-brand-600" style={{ width: `${(done / steps.length) * 100}%` }} />
      </div>
      <ol className="space-y-2">
        {steps.map((step) => (
          <li key={step.key}>
            <Link to={step.to} className="flex items-center gap-3 rounded-lg px-2 py-2 hover:bg-slate-50">
              <span
                className={cx(
                  "flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-xs font-bold",
                  step.done ? "bg-brand-600 text-white" : "ring-2 ring-slate-300 text-transparent",
                )}
              >
                ✓
              </span>
              <span className={cx("text-sm", step.done ? "text-slate-400 line-through" : "font-medium text-slate-800")}>{t(step.key)}</span>
              {!step.done && <span className="ml-auto text-brand-700">→</span>}
            </Link>
          </li>
        ))}
      </ol>
    </Card>
  );
}

function TrialBanner() {
  const { t } = useI18n();
  const owner = useCurrentShop()?.role === "owner";
  const shop = useQuery({ queryKey: ["shop"], queryFn: () => get<{ shop: Shop }>("/api/me") });
  const s = shop.data?.shop;
  if (!s || s.plan !== "trial" || !s.trial_ends_at) return null;
  const days = Math.ceil((new Date(s.trial_ends_at).getTime() - Date.now()) / 86_400_000);
  const over = days <= 0;
  return (
    <div className={cx("mb-6 rounded-xl px-4 py-3 text-sm font-medium", over ? "bg-red-50 text-red-800 ring-1 ring-red-200" : "bg-amber-50 text-amber-900 ring-1 ring-amber-200")}>
      {over ? t("dash.trial_over") : t("dash.trial_left", { days })}{" "}
      {owner && (
        <Link to="/billing" className="whitespace-nowrap font-semibold underline">
          {t("dash.choose_plan")} →
        </Link>
      )}
    </div>
  );
}

export function DashboardPage() {
  const { t, money } = useI18n();
  const owner = useCurrentShop()?.role === "owner";
  const [table, setTable] = useState(false);
  const stats = useQuery({ queryKey: ["stats"], queryFn: () => get<Stats>("/api/stats?days=30") });
  const daily = useQuery({ queryKey: ["daily"], queryFn: () => get<DailyPoint[]>("/api/stats/daily?days=30") });
  const st = stats.data;
  const series: { key: "conversations" | "orders" | "leads"; label: MessageKey; color: string }[] = [
    { key: "conversations", label: "dash.conversations", color: "#0d9488" },
    { key: "orders", label: "dash.ai_orders", color: "#0f766e" },
    { key: "leads", label: "dash.leads", color: "#0f766e" },
  ];
  return (
    <>
      <PageHeader title={t("dash.title")} subtitle={t("dash.period")} />
      <TrialBanner />
      {owner && <SetupChecklist />}
      <ErrorBox error={stats.error} />
      {st ? (
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
          <Tile label={t("dash.ai_orders")} value={String(st.orders)} sub={money(st.ai_orders_revenue)} />
          <Tile label={t("dash.conversations")} value={String(st.conversations)} sub={`${t("dash.conversion")}: ${(st.conversion * 100).toFixed(1)}%`} />
          <Tile label={t("dash.leads")} value={String(st.leads)} sub={`${t("dash.handoffs")}: ${st.handoffs}`} />
          <Tile
            label={t("dash.limit")}
            value={`${st.month_conversations} / ${st.month_limit}`}
            sub={`${t("dash.ai_cost")}: ${money(Number(st.ai_cost))}`}
          />
        </div>
      ) : (
        <Loading />
      )}
      <Card
        className="mt-6"
        title={t("dash.daily")}
        actions={
          <Button variant="ghost" size="sm" onClick={() => setTable(!table)}>
            {table ? t("dash.hide_table") : t("dash.show_table")}
          </Button>
        }
      >
        {daily.data &&
          (table ? (
            <div className="max-h-80 overflow-auto">
              <table className="w-full text-sm">
                <thead className="sticky top-0 bg-white text-left text-slate-500">
                  <tr>
                    <th className="py-2 font-medium">{t("dash.date")}</th>
                    {series.map((s) => (
                      <th key={s.key} className="py-2 text-right font-medium">
                        {t(s.label)}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {[...daily.data].reverse().map((p) => (
                    <tr key={p.date}>
                      <td className="py-1.5 text-slate-600">{`${p.date.slice(8, 10)}.${p.date.slice(5, 7)}.${p.date.slice(0, 4)}`}</td>
                      {series.map((s) => (
                        <td key={s.key} className="py-1.5 text-right tabular-nums text-slate-800">
                          {p[s.key]}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="grid gap-6 md:grid-cols-3">
              {series.map((s) => (
                <DailyBars key={s.key} title={t(s.label)} color={s.color} points={daily.data.map((p) => ({ date: p.date, value: p[s.key] }))} />
              ))}
            </div>
          ))}
      </Card>
    </>
  );
}
