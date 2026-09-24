import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { del, get, patch, post } from "../api";
import { useI18n } from "../i18n";
import type { StaffMember } from "../types";
import { Badge, Button, Card, ErrorBox, Input, Loading, Modal, PageHeader, Select } from "../ui";
import { CopyButton } from "./Connect";

function InviteLink({ member }: { member: StaffMember }) {
  const { t } = useI18n();
  if (!member.invite_url) return null;
  // PUBLIC_WEB_URL sozlanmagan bo'lsa backend nisbiy yo'l qaytaradi
  const url = member.invite_url.startsWith("/") ? window.location.origin + member.invite_url : member.invite_url;
  return (
    <div className="space-y-2 rounded-xl bg-brand-50 p-4 ring-1 ring-brand-100">
      <p className="text-sm text-brand-900">{t("staff.invite_hint", { name: member.name })}</p>
      <div className="flex flex-wrap items-center gap-2">
        <code className="max-w-full break-all rounded-lg bg-white px-3 py-2 text-xs text-brand-900 ring-1 ring-slate-200">{url}</code>
        <CopyButton text={url} />
      </div>
    </div>
  );
}

export function StaffPage() {
  const { t } = useI18n();
  const qc = useQueryClient();
  const staff = useQuery({ queryKey: ["staff"], queryFn: () => get<StaffMember[]>("/api/staff") });
  const [adding, setAdding] = useState(false);
  const [form, setForm] = useState({ name: "", phone: "+998 ", role: "operator" });
  const [invite, setInvite] = useState<StaffMember | null>(null);
  const refresh = () => qc.invalidateQueries({ queryKey: ["staff"] });

  const add = useMutation({
    mutationFn: () => post<StaffMember>("/api/staff", form),
    onSuccess: (m) => {
      refresh();
      setAdding(false);
      setForm({ name: "", phone: "+998 ", role: "operator" });
      if (m.invite_url) setInvite(m);
    },
  });
  const update = useMutation({
    mutationFn: ({ id, body }: { id: number; body: { role?: string; notify?: boolean } }) => patch(`/api/staff/${id}`, body),
    onSuccess: refresh,
  });
  const reinvite = useMutation({
    mutationFn: (id: number) => post<StaffMember>(`/api/staff/${id}/invite`),
    onSuccess: setInvite,
  });
  const remove = useMutation({ mutationFn: (id: number) => del(`/api/staff/${id}`), onSuccess: refresh });

  return (
    <>
      <PageHeader title={t("staff.title")} subtitle={t("staff.subtitle")} actions={<Button onClick={() => setAdding(true)}>+ {t("staff.add")}</Button>} />
      <ErrorBox error={staff.error ?? update.error ?? remove.error ?? reinvite.error} />
      <div className="mb-6 grid gap-3 text-sm sm:grid-cols-2">
        <div className="rounded-xl bg-white p-4 ring-1 ring-slate-100">
          <p className="font-semibold text-brand-900">{t("staff.role.owner")}</p>
          <p className="mt-1 text-slate-600">{t("staff.role.owner_hint")}</p>
        </div>
        <div className="rounded-xl bg-white p-4 ring-1 ring-slate-100">
          <p className="font-semibold text-brand-900">{t("staff.role.operator")}</p>
          <p className="mt-1 text-slate-600">{t("staff.role.operator_hint")}</p>
        </div>
      </div>
      {staff.isLoading ? (
        <Loading />
      ) : (
        <Card flush>
          <ul className="divide-y divide-slate-100">
            {staff.data?.map((m) => (
              <li key={m.id} className="flex flex-col gap-3 px-5 py-4 sm:flex-row sm:items-center">
                <div className="min-w-0 flex-1">
                  <p className="flex flex-wrap items-center gap-2 font-medium text-slate-900">
                    {m.name}
                    {m.is_me && <Badge tone="brand">{t("staff.you")}</Badge>}
                    {m.pending && <Badge tone="gold">{t("staff.pending")}</Badge>}
                  </p>
                  <p className="text-sm text-slate-500">
                    {m.phone ?? "—"} · {m.telegram_linked ? `✈ ${t("staff.tg_linked")}` : t("staff.tg_not_linked")}
                  </p>
                </div>
                <div className="flex flex-wrap items-center gap-3 sm:flex-nowrap">
                  <label className="flex items-center gap-2 whitespace-nowrap text-sm text-slate-600">
                    <input
                      type="checkbox"
                      checked={m.notify}
                      onChange={(e) => update.mutate({ id: m.id, body: { notify: e.target.checked } })}
                      className="h-4 w-4 rounded border-slate-300 accent-brand-700"
                    />
                    {t("staff.notify")}
                  </label>
                  <Select
                    aria-label={t("staff.role")}
                    value={m.role}
                    disabled={m.is_me}
                    onChange={(e) => update.mutate({ id: m.id, body: { role: e.target.value } })}
                    className="w-auto py-1.5 text-sm"
                  >
                    <option value="owner">{t("staff.role.owner")}</option>
                    <option value="operator">{t("staff.role.operator")}</option>
                  </Select>
                  {m.pending && (
                    <Button size="sm" variant="secondary" loading={reinvite.isPending && reinvite.variables === m.id} onClick={() => reinvite.mutate(m.id)}>
                      {t("staff.link")}
                    </Button>
                  )}
                  {!m.is_me && (
                    <Button
                      size="sm"
                      variant="danger"
                      onClick={() => window.confirm(t("staff.remove_confirm", { name: m.name })) && remove.mutate(m.id)}
                    >
                      {t("common.delete")}
                    </Button>
                  )}
                </div>
              </li>
            ))}
          </ul>
        </Card>
      )}

      <Modal open={adding} onClose={() => setAdding(false)} title={t("staff.add")}>
        <form
          className="space-y-4"
          onSubmit={(e: FormEvent) => {
            e.preventDefault();
            add.mutate();
          }}
        >
          <Input label={t("auth.name")} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required />
          <Input label={t("auth.phone")} type="tel" value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} required />
          <Select label={t("staff.role")} value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}>
            <option value="operator">{t("staff.role.operator")}</option>
            <option value="owner">{t("staff.role.owner")}</option>
          </Select>
          <ErrorBox error={add.error} />
          <div className="flex justify-end gap-2">
            <Button type="button" variant="ghost" onClick={() => setAdding(false)}>
              {t("common.cancel")}
            </Button>
            <Button type="submit" loading={add.isPending}>
              {t("common.add")}
            </Button>
          </div>
        </form>
      </Modal>

      <Modal open={!!invite} onClose={() => setInvite(null)} title={t("staff.invite_title")}>
        {invite && <InviteLink member={invite} />}
      </Modal>
    </>
  );
}
