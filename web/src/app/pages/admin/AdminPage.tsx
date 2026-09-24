import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { get, post } from "../../api";
import { useI18n } from "../../i18n";
import type { AdminOverview, AdminShopDetail, AdminShopRow } from "../../types";
import { Badge, Button, Card, Empty, ErrorBox, Input, Loading, Modal, PageHeader, Select } from "../../ui";

const PLAN_PRICE: Record<string, number> = { start: 149_000, business: 299_000, pro: 599_000 };

function Tile({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-2xl bg-white p-4 shadow-sm ring-1 ring-slate-100">
      <p className="text-xs text-slate-500">{label}</p>
      <p className="mt-1.5 text-xl font-bold text-slate-900">{value}</p>
    </div>
  );
}

function ShopDetail({ id }: { id: number }) {
  const { t, money, date } = useI18n();
  const qc = useQueryClient();
  const detail = useQuery({ queryKey: ["admin", "shop", id], queryFn: () => get<AdminShopDetail>(`/api/admin/shops/${id}`) });
  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["admin"] });
  };
  const action = useMutation({
    mutationFn: ({ path, body }: { path: string; body: unknown }) => post(`/api/admin/shops/${id}/${path}`, body),
    onSuccess: refresh,
  });
  const [pay, setPay] = useState({ plan: "business", months: "1", amount: "299000", note: "" });
  if (!detail.data) return detail.error ? <ErrorBox error={detail.error} /> : <Loading />;
  const s = detail.data.shop;
  const submitPay = (e: FormEvent) => {
    e.preventDefault();
    action.mutate({
      path: "payments",
      body: { plan: pay.plan, months: Number(pay.months), amount: Number(pay.amount.replace(/\s/g, "")), note: pay.note || null },
    });
  };
  return (
    <div className="space-y-5">
      <dl className="grid grid-cols-2 gap-3 text-sm">
        <div>
          <dt className="text-slate-500">{t("admin.owner")}</dt>
          <dd>
            {s.owner_name} {s.owner_phone && <span className="text-slate-500">· {s.owner_phone}</span>}
          </dd>
        </div>
        <div>
          <dt className="text-slate-500">{t("admin.plan")}</dt>
          <dd>
            <Badge tone={s.status === "active" ? "brand" : "red"}>{s.plan}</Badge> {s.status !== "active" && <Badge tone="red">{s.status}</Badge>}
          </dd>
        </div>
        <div>
          <dt className="text-slate-500">{t("admin.trial_until")}</dt>
          <dd>{s.trial_ends_at ? date(s.trial_ends_at) : "—"}</dd>
        </div>
        <div>
          <dt className="text-slate-500">{t("admin.paid_until")}</dt>
          <dd>{s.paid_until ? date(s.paid_until) : "—"}</dd>
        </div>
      </dl>
      <ErrorBox error={action.error} />
      <div className="flex flex-wrap gap-2">
        <Button size="sm" variant="secondary" onClick={() => action.mutate({ path: "plan", body: { trial_days: 7 } })}>
          {t("admin.extend_trial")}
        </Button>
        {s.status === "active" ? (
          <Button size="sm" variant="danger" onClick={() => action.mutate({ path: "status", body: { status: "paused" } })}>
            {t("admin.pause")}
          </Button>
        ) : (
          <Button size="sm" onClick={() => action.mutate({ path: "status", body: { status: "active" } })}>
            {t("admin.activate")}
          </Button>
        )}
      </div>
      <form onSubmit={submitPay} className="space-y-3 rounded-xl bg-slate-50 p-4">
        <p className="text-sm font-semibold text-brand-900">{t("admin.add_payment")}</p>
        <div className="grid gap-3 sm:grid-cols-3">
          <Select
            label={t("admin.plan")}
            value={pay.plan}
            onChange={(e) => setPay({ ...pay, plan: e.target.value, amount: String(PLAN_PRICE[e.target.value] * Number(pay.months)) })}
          >
            {Object.keys(PLAN_PRICE).map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </Select>
          <Input
            label={t("admin.months")}
            type="number"
            min={1}
            max={24}
            value={pay.months}
            onChange={(e) => setPay({ ...pay, months: e.target.value, amount: String(PLAN_PRICE[pay.plan] * Number(e.target.value || 1)) })}
          />
          <Input label={t("admin.amount")} inputMode="numeric" value={pay.amount} onChange={(e) => setPay({ ...pay, amount: e.target.value })} />
        </div>
        <Input label={t("admin.note")} value={pay.note} onChange={(e) => setPay({ ...pay, note: e.target.value })} />
        <Button type="submit" size="sm" loading={action.isPending}>
          {t("admin.add_payment")}
        </Button>
      </form>
      <div>
        <p className="mb-2 text-sm font-semibold text-brand-900">{t("admin.payments")}</p>
        {detail.data.payments.length ? (
          <ul className="divide-y divide-slate-100 text-sm">
            {detail.data.payments.map((p) => (
              <li key={p.id} className="flex justify-between py-2">
                <span className="text-slate-600">
                  {date(p.created_at)} · {p.provider} {p.provider_txn_id && `· ${p.provider_txn_id}`}
                </span>
                <span className="font-medium tabular-nums">{money(p.amount)}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-slate-400">—</p>
        )}
      </div>
    </div>
  );
}

export function AdminPage() {
  const { t, money, date } = useI18n();
  const [q, setQ] = useState("");
  const [selected, setSelected] = useState<AdminShopRow | null>(null);
  const overview = useQuery({ queryKey: ["admin", "overview"], queryFn: () => get<AdminOverview>("/api/admin/overview") });
  const shops = useQuery({
    queryKey: ["admin", "shops", q],
    queryFn: () => get<AdminShopRow[]>(`/api/admin/shops?limit=200${q ? `&q=${encodeURIComponent(q)}` : ""}`),
  });
  const o = overview.data;
  return (
    <>
      <PageHeader title={t("admin.title")} />
      <ErrorBox error={overview.error ?? shops.error} />
      {o && (
        <div className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
          <Tile label={t("admin.shops")} value={String(o.shops)} />
          <Tile label={t("admin.trials")} value={String(o.trials_active)} />
          <Tile label={t("admin.paying")} value={String(o.paying)} />
          <Tile label={t("admin.mrr")} value={money(o.mrr)} />
          <Tile label={t("admin.month_revenue")} value={money(o.month_revenue)} />
          <Tile label={t("admin.month_cost")} value={money(Number(o.month_ai_cost))} />
        </div>
      )}
      <Input placeholder={t("common.search")} value={q} onChange={(e) => setQ(e.target.value)} className="mb-4 max-w-sm" />
      {shops.isLoading ? (
        <Loading />
      ) : shops.data?.length ? (
        <Card flush className="overflow-x-auto">
          <table className="w-full min-w-[820px] text-sm">
            <thead className="border-b border-slate-100 text-left text-slate-500">
              <tr>
                <th className="px-4 py-3 font-medium">{t("admin.shops")}</th>
                <th className="px-4 py-3 font-medium">{t("admin.owner")}</th>
                <th className="px-4 py-3 font-medium">{t("admin.plan")}</th>
                <th className="px-4 py-3 font-medium">{t("admin.paid_until")}</th>
                <th className="px-4 py-3 text-right font-medium">{t("admin.usage")}</th>
                <th className="px-4 py-3 text-right font-medium">{t("dash.ai_orders")}</th>
                <th className="px-4 py-3 font-medium">{t("admin.business")}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {shops.data.map((s) => (
                <tr key={s.id} onClick={() => setSelected(s)} className="cursor-pointer hover:bg-slate-50">
                  <td className="px-4 py-3 font-medium text-slate-900">{s.name}</td>
                  <td className="px-4 py-3 text-slate-600">
                    {s.owner_name}
                    <div className="text-xs text-slate-400">{s.owner_phone}</div>
                  </td>
                  <td className="px-4 py-3">
                    <Badge tone={s.status !== "active" ? "red" : s.plan === "trial" ? "gold" : "brand"}>{s.status !== "active" ? s.status : s.plan}</Badge>
                  </td>
                  <td className="px-4 py-3 text-slate-600">
                    {s.paid_until ? date(s.paid_until) : s.trial_ends_at ? `${t("admin.trial_until")}: ${date(s.trial_ends_at)}` : "—"}
                  </td>
                  <td className="px-4 py-3 text-right tabular-nums">{s.month_conversations}</td>
                  <td className="px-4 py-3 text-right tabular-nums">{s.orders_30d}</td>
                  <td className="px-4 py-3">{s.business_connected ? "✓" : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      ) : (
        <Empty />
      )}
      <Modal open={!!selected} onClose={() => setSelected(null)} title={selected?.name ?? ""}>
        {selected && <ShopDetail id={selected.id} />}
      </Modal>
    </>
  );
}
