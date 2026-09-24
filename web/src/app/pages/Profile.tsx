import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState, type FormEvent } from "react";
import { patch, post } from "../api";
import { useMe } from "../auth";
import { useI18n } from "../i18n";
import { LangSwitch } from "../Layout";
import type { Account } from "../types";
import { TelegramLinkCard } from "./Connect";
import { Button, Card, ErrorBox, Input, Loading, PageHeader, SavedFlash } from "../ui";

export function ProfilePage() {
  const { t } = useI18n();
  const qc = useQueryClient();
  const { data: me } = useMe();
  const [name, setName] = useState("");
  const [pw, setPw] = useState({ old_password: "", new_password: "", phone: "+998 " });
  useEffect(() => {
    if (me) setName(me.name);
  }, [me]);
  const saveName = useMutation({
    mutationFn: () => patch<Account>("/api/auth/me", { name }),
    onSuccess: (a) => qc.setQueryData(["me"], a),
  });
  const savePw = useMutation({
    mutationFn: () =>
      post<Account>("/api/auth/password", {
        old_password: me?.has_password ? pw.old_password : null,
        new_password: pw.new_password,
        phone: me?.phone ? null : pw.phone,
      }),
    onSuccess: (a) => {
      qc.setQueryData(["me"], a);
      setPw({ old_password: "", new_password: "", phone: "+998 " });
    },
  });
  if (!me) return <Loading />;
  return (
    <>
      <PageHeader title={t("profile.title")} />
      <div className="max-w-xl space-y-6">
        <Card>
          <form
            className="space-y-4"
            onSubmit={(e: FormEvent) => {
              e.preventDefault();
              saveName.mutate();
            }}
          >
            <Input label={t("auth.name")} value={name} onChange={(e) => setName(e.target.value)} required />
            {me.phone && <Input label={t("auth.phone")} value={me.phone} disabled />}
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <span className="text-sm font-medium text-slate-700">{t("profile.lang")}</span>
                <LangSwitch />
              </div>
              <div className="flex items-center gap-3">
                <SavedFlash show={saveName.isSuccess && !saveName.isPending} />
                <Button type="submit" loading={saveName.isPending}>
                  {t("common.save")}
                </Button>
              </div>
            </div>
            <ErrorBox error={saveName.error} />
          </form>
        </Card>
        <TelegramLinkCard />
        <Card title={me.has_password ? t("profile.password") : t("profile.set_password")}>
          <form
            className="space-y-4"
            onSubmit={(e: FormEvent) => {
              e.preventDefault();
              savePw.mutate();
            }}
          >
            {!me.phone && <Input label={t("auth.phone")} type="tel" value={pw.phone} onChange={(e) => setPw({ ...pw, phone: e.target.value })} required />}
            {me.has_password && (
              <Input
                label={t("profile.old_password")}
                type="password"
                autoComplete="current-password"
                value={pw.old_password}
                onChange={(e) => setPw({ ...pw, old_password: e.target.value })}
                required
              />
            )}
            <Input
              label={t("profile.new_password")}
              hint={t("auth.password_hint")}
              type="password"
              autoComplete="new-password"
              minLength={8}
              value={pw.new_password}
              onChange={(e) => setPw({ ...pw, new_password: e.target.value })}
              required
            />
            <ErrorBox error={savePw.error} />
            <div className="flex items-center justify-end gap-3">
              <SavedFlash show={savePw.isSuccess && !savePw.isPending} />
              <Button type="submit" loading={savePw.isPending}>
                {t("common.save")}
              </Button>
            </div>
          </form>
        </Card>
      </div>
    </>
  );
}
