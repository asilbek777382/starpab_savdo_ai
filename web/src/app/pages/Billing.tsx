import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { get, post } from "../api";
import { useCurrentShop } from "../auth";
import { useI18n } from "../i18n";
import type { MessageKey } from "../locales";
import type { Billing, PlanInfo } from "../types";
import { Badge, Button, Card, cx, ErrorBox, Loading, PageHeader } from "../ui";

const MONTHS = [1, 3, 6, 12] as const;
const PROVIDER_NAME = { payme: "Payme", click: "Click" } as const;

function planTotal(p: PlanInfo, months: number, discount: number) {
  const total = p.price * months;
  return months === 12 ? Math.round(total * (1 - discount)) : total;
}

export function BillingPage() {
  const { t, money, date } = useI18n();
  const shop = useCurrentShop();
  const [params] = useSearchParams();
  const [months, setMonths] = useState<(typeof MONTHS)[number]>(1);
  const billing = useQuery({ queryKey: ["billing"], queryFn: () => get<Billing>("/api/billing") });
  const checkout = useMutation({
    mutationFn: (body: { plan: string; months: number; provider: string }) =>
      post<{ url: string }>("/api/billing/checkout", body),
    onSuccess: (r) => window.location.assign(r.url),
  });

  if (billing.isLoading) return <Loading />;
  const b = billing.data;
  if (!b) return <ErrorBox error={billing.error} />;
  const isOwner = shop?.role === "owner";
  const discountPct = Math.round(b.yearly_discount * 100);
  const planName = (code: string) => t(`billing.plan.${code}` as MessageKey);

  return (
    <>
      <PageHeader title={t("billing.title")} subtitle={t("billing.subtitle")} />
      {params.get("paid") && (
        <div className="mb-4 rounded-xl bg-emerald-50 px-4 py-3 text-sm text-emerald-800 ring-1 ring-emerald-100">
          {t("billing.thanks")}
        </div>
      )}
      <ErrorBox error={checkout.error} />

      <div className="mb-6 grid gap-4 sm:grid-cols-3">
        <div className="rounded-2xl bg-white p-5 shadow-sm ring-1 ring-slate-100">
          <p className="text-sm text-slate-500">{t("billing.current")}</p>
          <p className="mt-2 flex items-center gap-2 text-2xl font-bold text-slate-900">
            {planName(b.plan)}
            {b.status !== "active" && <Badge tone="red">{b.status}</Badge>}
          </p>
        </div>
        <div className="rounded-2xl bg-white p-5 shadow-sm ring-1 ring-slate-100">
          <p className="text-sm text-slate-500">{b.paid_until ? t("billing.paid_until") : t("billing.trial_until")}</p>
          <p className="mt-2 text-2xl font-bold text-slate-900">
            {b.paid_until ? date(b.paid_until, false) : b.trial_ends_at ? date(b.trial_ends_at, false) : "—"}
          </p>
        </div>
        <div className="rounded-2xl bg-white p-5 shadow-sm ring-1 ring-slate-100">
          <p className="text-sm text-slate-500">{t("billing.usage")}</p>
          <p className="mt-2 text-2xl font-bold text-slate-900">
            {b.month_conversations} <span className="text-base font-medium text-slate-400">/ {b.month_limit}</span>
          </p>
          <div className="mt-2 h-1.5 rounded-full bg-slate-100">
            <div
              className="h-1.5 rounded-full bg-brand-700"
              style={{ width: `${Math.min(100, (b.month_conversations / Math.max(1, b.month_limit)) * 100)}%` }}
            />
          </div>
        </div>
      </div>

      <div className="mb-4 flex flex-wrap items-center gap-3">
        <span className="text-sm font-medium text-slate-600">{t("billing.period")}:</span>
        <div className="flex flex-wrap rounded-full bg-white p-1 ring-1 ring-slate-200" role="group" aria-label={t("billing.period")}>
          {MONTHS.map((m) => (
            <button
              key={m}
              type="button"
              aria-pressed={months === m}
              onClick={() => setMonths(m)}
              className={cx(
                "whitespace-nowrap rounded-full px-3.5 py-1.5 text-sm font-semibold",
                months === m ? "bg-brand-700 text-white" : "text-slate-600",
              )}
            >
              {m === 12 ? t("billing.yearly", { p: discountPct }) : t("billing.months", { n: m })}
            </button>
          ))}
        </div>
      </div>

      {!b.providers.length && (
        <div className="mb-4 rounded-xl bg-amber-50 px-4 py-3 text-sm text-amber-800 ring-1 ring-amber-100">
          {t("billing.no_providers")}
        </div>
      )}
      {b.providers.length > 0 && !isOwner && (
        <div className="mb-4 rounded-xl bg-slate-100 px-4 py-3 text-sm text-slate-600">{t("billing.owner_only")}</div>
      )}

      <div className="grid gap-4 md:grid-cols-3">
        {b.plans.map((p) => {
          const total = planTotal(p, months, b.yearly_discount);
          const current = b.plan === p.code;
          const popular = p.code === "business";
          return (
            <section
              key={p.code}
              className={cx(
                "flex flex-col rounded-2xl bg-white p-5 shadow-sm ring-1 sm:p-6",
                popular ? "ring-2 ring-gold-500" : "ring-slate-100",
              )}
            >
              <div className="flex items-center justify-between gap-2">
                <h2 className="text-lg font-bold text-brand-900">{planName(p.code)}</h2>
                {current ? <Badge tone="green">{t("billing.current")}</Badge> : popular && <Badge tone="gold">{t("billing.popular")}</Badge>}
              </div>
              <p className="mt-3 text-2xl font-bold text-slate-900">
                {money(Math.round(total / months))}
                <span className="ml-1 text-sm font-medium text-slate-400">/ {t("billing.per_month")}</span>
              </p>
              {months > 1 && (
                <p className="text-sm text-slate-500">
                  {t("billing.total")}: <span className="font-semibold text-slate-700">{money(total)}</span>
                </p>
              )}
              <ul className="mt-4 space-y-1.5 text-sm text-slate-600">
                <li>✓ {t("billing.conversations", { n: p.conversations.toLocaleString("ru-RU") })}</li>
                <li>
                  ✓{" "}
                  {p.max_products === null
                    ? t("billing.products_unlimited")
                    : t("billing.products", { n: p.max_products.toLocaleString("ru-RU") })}
                </li>
                <li className={p.instagram ? "" : "text-slate-400"}>
                  {p.instagram ? `✓ ${t("billing.instagram")}` : `— ${t("billing.instagram_no")}`}
                </li>
              </ul>
              <div className="mt-auto flex flex-col gap-2 pt-5">
                {b.providers.map((prov) => (
                  <Button
                    key={prov}
                    variant={popular ? "gold" : "primary"}
                    disabled={!isOwner}
                    loading={checkout.isPending && checkout.variables?.plan === p.code && checkout.variables?.provider === prov}
                    onClick={() => checkout.mutate({ plan: p.code, months, provider: prov })}
                  >
                    {t("billing.pay_with", { p: PROVIDER_NAME[prov] })}
                  </Button>
                ))}
              </div>
            </section>
          );
        })}
      </div>

      {b.payments.length > 0 && (
        <Card flush className="mt-6 overflow-x-auto">
          <h2 className="px-5 pt-5 pb-2 text-base font-semibold text-brand-900">{t("billing.history")}</h2>
          <table className="w-full min-w-[520px] text-sm">
            <tbody className="divide-y divide-slate-100">
              {b.payments.map((p) => (
                <tr key={p.id}>
                  <td className="whitespace-nowrap px-5 py-3 text-slate-500">{date(p.created_at)}</td>
                  <td className="px-5 py-3 font-medium text-slate-900">
                    {p.plan ? planName(p.plan) : "—"} · {t("billing.months", { n: p.months })}
                  </td>
                  <td className="whitespace-nowrap px-5 py-3">{money(p.amount)}</td>
                  <td className="px-5 py-3 capitalize text-slate-500">{p.provider}</td>
                  <td className="px-5 py-3">
                    <Badge tone={p.status === "paid" ? "green" : "gray"}>
                      {p.status === "paid" || p.status === "cancelled" ? t(`billing.status.${p.status}`) : p.status}
                    </Badge>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </>
  );
}
