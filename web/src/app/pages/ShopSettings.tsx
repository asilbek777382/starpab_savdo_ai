import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState, type FormEvent } from "react";
import { get, put } from "../api";
import { useI18n } from "../i18n";
import type { DeliveryZone, Settings, Shop } from "../types";
import { Button, Card, ErrorBox, Input, Loading, PageHeader, SavedFlash, Textarea } from "../ui";
import { useSettings } from "../useSettings";

type ZoneDraft = { name: string; keywords: string; fee: string; eta: string; extra: Partial<DeliveryZone> };

export function ShopSettingsPage() {
  const { t } = useI18n();
  const qc = useQueryClient();
  const { query, save } = useSettings();
  const me = useQuery({ queryKey: ["shop"], queryFn: () => get<{ shop: Shop }>("/api/me") });
  const [s, setS] = useState<Settings | null>(null);
  const [zones, setZones] = useState<ZoneDraft[]>([]);
  const [shopName, setShopName] = useState("");
  useEffect(() => {
    if (!query.data) return;
    setS(query.data);
    setZones(
      query.data.delivery_zones.map(({ name, keywords, fee, eta, ...extra }) => ({
        name,
        keywords: keywords.join(", "),
        fee: String(fee),
        eta: eta ?? "",
        extra,
      })),
    );
  }, [query.data]);
  useEffect(() => {
    if (me.data) setShopName(me.data.shop.name);
  }, [me.data]);
  const saveShop = useMutation({
    mutationFn: () => put("/api/shop", { name: shopName }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["shop"] });
      qc.invalidateQueries({ queryKey: ["me"] });
    },
  });
  if (!s) return query.error ? <ErrorBox error={query.error} /> : <Loading />;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (me.data && shopName.trim() && shopName !== me.data.shop.name) await saveShop.mutateAsync();
    save.mutate({
      ...s,
      delivery_zones: zones
        .filter((z) => z.name.trim())
        .map((z) => ({
          ...z.extra,
          name: z.name.trim(),
          keywords: z.keywords
            .split(",")
            .map((k) => k.trim())
            .filter(Boolean),
          fee: Number(z.fee.replace(/\s/g, "")) || 0,
          eta: z.eta.trim() || null,
        })),
    });
  };
  const setZone = (i: number, k: keyof Omit<ZoneDraft, "extra">, v: string) => setZones(zones.map((z, j) => (j === i ? { ...z, [k]: v } : z)));
  return (
    <form onSubmit={submit}>
      <PageHeader
        title={t("shop.title")}
        actions={
          <div className="flex items-center gap-3">
            <SavedFlash show={save.isSuccess && !save.isPending} />
            <Button type="submit" loading={save.isPending || saveShop.isPending}>
              {t("common.save")}
            </Button>
          </div>
        }
      />
      <ErrorBox error={save.error ?? saveShop.error} />
      <div className="space-y-6">
        <Card>
          <div className="space-y-5">
            <Input label={t("shop.name")} value={shopName} onChange={(e) => setShopName(e.target.value)} required />
            <Textarea label={t("shop.faq")} hint={t("shop.faq_hint")} rows={6} value={s.faq_text} onChange={(e) => setS({ ...s, faq_text: e.target.value })} />
            <div className="grid gap-4 sm:grid-cols-2">
              <Input label={t("shop.address")} value={s.address} onChange={(e) => setS({ ...s, address: e.target.value })} />
              <Input label={t("shop.hours")} value={s.working_hours} onChange={(e) => setS({ ...s, working_hours: e.target.value })} placeholder="10:00–21:00" />
            </div>
            <Input label={t("shop.payments")} value={s.payment_methods} onChange={(e) => setS({ ...s, payment_methods: e.target.value })} placeholder="Naqd, Click, Payme" />
          </div>
        </Card>
        <Card title={t("shop.zones")}>
          <div className="space-y-3">
            {zones.map((z, i) => (
              <div key={i} className="grid gap-2 rounded-xl bg-slate-50 p-3 sm:grid-cols-[1.2fr_2fr_0.8fr_0.8fr_auto] sm:items-end">
                <Input label={t("shop.zone_name")} value={z.name} onChange={(e) => setZone(i, "name", e.target.value)} placeholder="Toshkent" />
                <Input label={t("shop.zone_keywords")} value={z.keywords} onChange={(e) => setZone(i, "keywords", e.target.value)} placeholder="chilonzor, yunusobod" />
                <Input label={t("shop.zone_fee")} inputMode="numeric" value={z.fee} onChange={(e) => setZone(i, "fee", e.target.value)} />
                <Input label={t("shop.zone_eta")} value={z.eta} onChange={(e) => setZone(i, "eta", e.target.value)} placeholder="1 kun" />
                <button type="button" aria-label={t("common.delete")} onClick={() => setZones(zones.filter((_, j) => j !== i))} className="rounded-lg p-2.5 text-slate-400 hover:bg-red-50 hover:text-red-600">
                  ✕
                </button>
              </div>
            ))}
          </div>
          <Button type="button" variant="ghost" size="sm" className="mt-3" onClick={() => setZones([...zones, { name: "", keywords: "", fee: "", eta: "", extra: {} }])}>
            + {t("shop.add_zone")}
          </Button>
        </Card>
      </div>
    </form>
  );
}
