import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { get, post } from "../api";
import { useI18n } from "../i18n";
import type { Order } from "../types";
import { Badge, Button, Card, cx, Empty, ErrorBox, Loading, PageHeader } from "../ui";

const STATUS_TONE = { new: "gold", confirmed: "brand", shipped: "green", cancelled: "gray" } as const;
const STATUSES = ["new", "confirmed", "shipped", "cancelled"] as const;

export function OrderStatusBadge({ status }: { status: Order["status"] }) {
  const { t } = useI18n();
  return <Badge tone={STATUS_TONE[status]}>{t(`orders.status.${status}`)}</Badge>;
}

function OrderCard({ order }: { order: Order }) {
  const { t, money, date } = useI18n();
  const qc = useQueryClient();
  const change = useMutation({
    mutationFn: (status: string) => post<Order>(`/api/orders/${order.id}/status`, { status }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["orders"] }),
  });
  return (
    <Card>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-lg font-semibold text-slate-900">
            #{order.number} {order.source === "test" && <Badge>{t("orders.test")}</Badge>}
          </p>
          <p className="text-sm text-slate-500">{date(order.created_at)}</p>
        </div>
        <OrderStatusBadge status={order.status} />
      </div>
      <ul className="mt-4 space-y-1 text-sm">
        {order.items.map((it, i) => (
          <li key={i} className="flex justify-between gap-4">
            <span className="text-slate-700">
              {it.name}
              {Object.values(it.attrs).filter(Boolean).length > 0 && ` (${Object.values(it.attrs).filter(Boolean).join(", ")})`} × {it.qty}
            </span>
            <span className="tabular-nums text-slate-900">{money(it.line_total)}</span>
          </li>
        ))}
        <li className="flex justify-between text-slate-500">
          <span>{t("orders.delivery")}</span>
          <span className="tabular-nums">{money(order.delivery_fee)}</span>
        </li>
        <li className="flex justify-between border-t border-slate-100 pt-1 font-semibold">
          <span>{t("orders.total")}</span>
          <span className="tabular-nums">{money(order.total)}</span>
        </li>
      </ul>
      <dl className="mt-4 grid gap-1 text-sm sm:grid-cols-2">
        <div>
          <dt className="text-slate-500">{t("orders.customer")}</dt>
          <dd className="text-slate-800">
            {order.customer_name} ·{" "}
            <a className="text-brand-700 hover:underline" href={`tel:${order.phone}`}>
              {order.phone}
            </a>
          </dd>
        </div>
        <div>
          <dt className="text-slate-500">{t("orders.address")}</dt>
          <dd className="text-slate-800">
            {order.address || "—"}
            {order.location && (
              <a
                className="ml-2 text-brand-700 hover:underline"
                target="_blank"
                rel="noreferrer"
                href={`https://maps.google.com/?q=${order.location.latitude},${order.location.longitude}`}
              >
                {t("orders.map")}
              </a>
            )}
          </dd>
        </div>
        {order.comment && (
          <div className="sm:col-span-2">
            <dt className="text-slate-500">{t("orders.comment")}</dt>
            <dd className="whitespace-pre-line text-slate-800">{order.comment}</dd>
          </div>
        )}
      </dl>
      <ErrorBox error={change.error} />
      <div className="mt-4 flex flex-wrap gap-2">
        {order.status === "new" && (
          <Button size="sm" onClick={() => change.mutate("confirmed")} loading={change.isPending}>
            {t("orders.confirm")}
          </Button>
        )}
        {order.status === "confirmed" && (
          <Button size="sm" onClick={() => change.mutate("shipped")} loading={change.isPending}>
            {t("orders.ship")}
          </Button>
        )}
        {(order.status === "new" || order.status === "confirmed") && (
          <Button size="sm" variant="danger" onClick={() => change.mutate("cancelled")}>
            {t("orders.cancel")}
          </Button>
        )}
      </div>
    </Card>
  );
}

export function OrdersPage() {
  const { t } = useI18n();
  const [status, setStatus] = useState<string>("");
  const orders = useQuery({
    queryKey: ["orders", status],
    queryFn: () => get<Order[]>(`/api/orders?limit=100${status ? `&status=${status}` : ""}`),
  });
  return (
    <>
      <PageHeader title={t("orders.title")} />
      <div className="mb-4 flex flex-wrap gap-2">
        {["", ...STATUSES].map((s) => (
          <button
            key={s || "all"}
            onClick={() => setStatus(s)}
            className={cx(
              "rounded-full px-3 py-1.5 text-sm font-medium",
              status === s ? "bg-brand-700 text-white" : "bg-white text-slate-600 ring-1 ring-slate-200 hover:ring-brand-500",
            )}
          >
            {s ? t(`orders.status.${s as Order["status"]}`) : t("common.all")}
          </button>
        ))}
      </div>
      <ErrorBox error={orders.error} />
      {orders.isLoading ? (
        <Loading />
      ) : orders.data?.length ? (
        <div className="grid gap-4 lg:grid-cols-2">
          {orders.data.map((o) => (
            <OrderCard key={o.id} order={o} />
          ))}
        </div>
      ) : (
        <Empty />
      )}
    </>
  );
}
