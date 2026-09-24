import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { get, post } from "../api";
import { useI18n } from "../i18n";
import type { Lead } from "../types";
import { Badge, Card, Empty, ErrorBox, Loading, PageHeader, Select } from "../ui";

const TONE = { new: "gold", contacted: "blue", won: "green", lost: "gray" } as const;
const CHANNEL = { tg_business: "Telegram", tg_bot: "Telegram bot", instagram: "Instagram", test: "Test" } as Record<string, string>;

export function LeadsPage() {
  const { t, date } = useI18n();
  const qc = useQueryClient();
  const leads = useQuery({ queryKey: ["leads"], queryFn: () => get<Lead[]>("/api/leads?limit=200") });
  const setStatus = useMutation({
    mutationFn: ({ id, status }: { id: number; status: string }) => post(`/api/leads/${id}/status`, { status }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["leads"] }),
  });
  return (
    <>
      <PageHeader title={t("leads.title")} subtitle={t("leads.subtitle")} />
      <ErrorBox error={leads.error ?? setStatus.error} />
      {leads.isLoading ? (
        <Loading />
      ) : leads.data?.length ? (
        <Card flush className="overflow-x-auto">
          <table className="w-full min-w-[640px] text-sm">
            <thead className="border-b border-slate-100 text-left text-slate-500">
              <tr>
                <th className="px-5 py-3 font-medium">{t("orders.customer")}</th>
                <th className="px-5 py-3 font-medium">{t("leads.interest")}</th>
                <th className="px-5 py-3 font-medium">{t("orders.date")}</th>
                <th className="px-5 py-3 font-medium">{t("orders.status")}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {leads.data.map((l) => (
                <tr key={l.id} className="align-top">
                  <td className="px-5 py-3">
                    <p className="font-medium text-slate-900">{l.name || "—"}</p>
                    <a href={`tel:${l.phone}`} className="text-brand-700 hover:underline">
                      📞 {l.phone}
                    </a>
                    <p className="mt-0.5 text-xs text-slate-400">{CHANNEL[l.channel_type] ?? l.channel_type}</p>
                  </td>
                  <td className="px-5 py-3 text-slate-700">
                    {l.interest || "—"}
                    {l.note && <p className="text-xs text-slate-500">{l.note}</p>}
                    {l.conversation_id && (
                      <Link to={`/conversations?c=${l.conversation_id}`} className="text-xs text-brand-700 hover:underline">
                        💬 {t("nav.conversations")}
                      </Link>
                    )}
                  </td>
                  <td className="whitespace-nowrap px-5 py-3 text-slate-500">{date(l.created_at)}</td>
                  <td className="px-5 py-3">
                    <div className="flex flex-col gap-1.5">
                      <Badge tone={TONE[l.status]}>{t(`leads.status.${l.status}`)}</Badge>
                      <Select
                        aria-label={t("orders.status")}
                        value={l.status}
                        onChange={(e) => setStatus.mutate({ id: l.id, status: e.target.value })}
                        className="py-1.5 text-xs"
                      >
                        {(["new", "contacted", "won", "lost"] as const).map((s) => (
                          <option key={s} value={s}>
                            {t(`leads.status.${s}`)}
                          </option>
                        ))}
                      </Select>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      ) : (
        <Empty />
      )}
    </>
  );
}
