import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState, type FormEvent } from "react";
import { api, del, get, post, put } from "../api";
import { useI18n } from "../i18n";
import type { Category, Product, Variant } from "../types";
import { Badge, Button, Card, Empty, ErrorBox, Input, Loading, Modal, PageHeader, Textarea, Toggle } from "../ui";

type Draft = {
  id?: number;
  name: string;
  price: string;
  description: string;
  category_name: string;
  is_active: boolean;
  variants: { size: string; color: string; stock: string; price_override: string }[];
  images: string;
};

const emptyDraft = (): Draft => ({
  name: "",
  price: "",
  description: "",
  category_name: "",
  is_active: true,
  variants: [],
  images: "",
});

function toDraft(p: Product, categories: Category[]): Draft {
  const isDefault = p.variants.length === 1 && Object.keys(p.variants[0].attrs).length === 0;
  return {
    id: p.id,
    name: p.name,
    price: String(p.price),
    description: p.description,
    category_name: categories.find((c) => c.id === p.category_id)?.name ?? "",
    is_active: p.is_active,
    variants: isDefault
      ? []
      : p.variants.map((v) => ({
          size: v.attrs.size ?? "",
          color: v.attrs.color ?? "",
          stock: v.stock == null ? "" : String(v.stock),
          price_override: v.price_override == null ? "" : String(v.price_override),
        })),
    images: p.images.map((i) => i.url).join("\n"),
  };
}

const num = (s: string) => (s.trim() === "" ? null : Number(s.replace(/\s/g, "")));

function ProductEditor({ draft, categories, onClose }: { draft: Draft; categories: Category[]; onClose: () => void }) {
  const { t } = useI18n();
  const qc = useQueryClient();
  const [d, setD] = useState<Draft>(draft);
  const save = useMutation({
    mutationFn: () => {
      const variants: Variant[] = d.variants
        .filter((v) => v.size || v.color || v.stock || v.price_override)
        .map((v) => ({
          attrs: Object.fromEntries(Object.entries({ size: v.size.trim(), color: v.color.trim() }).filter(([, x]) => x)),
          stock: num(v.stock),
          price_override: num(v.price_override),
        }));
      const body = {
        name: d.name.trim(),
        price: num(d.price) ?? 0,
        description: d.description,
        category_name: d.category_name.trim() || null,
        is_active: d.is_active,
        variants,
        images: d.images
          .split("\n")
          .map((x) => x.trim())
          .filter(Boolean),
      };
      return d.id ? put(`/api/products/${d.id}`, body) : post("/api/products", body);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["products"] });
      qc.invalidateQueries({ queryKey: ["categories"] });
      onClose();
    },
  });
  const setVariant = (i: number, k: keyof Draft["variants"][number], v: string) =>
    setD({ ...d, variants: d.variants.map((x, j) => (j === i ? { ...x, [k]: v } : x)) });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    save.mutate();
  };
  return (
    <form onSubmit={submit} className="space-y-4">
      <div className="grid gap-4 sm:grid-cols-2">
        <Input label={t("cat.name")} value={d.name} onChange={(e) => setD({ ...d, name: e.target.value })} required />
        <Input label={t("cat.price")} inputMode="numeric" value={d.price} onChange={(e) => setD({ ...d, price: e.target.value })} required />
      </div>
      <Input
        label={t("cat.category")}
        list="nv-categories"
        value={d.category_name}
        onChange={(e) => setD({ ...d, category_name: e.target.value })}
      />
      <datalist id="nv-categories">
        {categories.map((c) => (
          <option key={c.id} value={c.name} />
        ))}
      </datalist>
      <Textarea label={t("cat.description")} rows={3} value={d.description} onChange={(e) => setD({ ...d, description: e.target.value })} />
      <div>
        <p className="text-sm font-medium text-slate-700">{t("cat.variants")}</p>
        <p className="mb-2 text-xs text-slate-500">{t("cat.variants_hint")}</p>
        <div className="space-y-2">
          {d.variants.map((v, i) => (
            <div key={i} className="grid grid-cols-[1fr_1fr_1fr_1fr_auto] items-center gap-2">
              <Input aria-label={t("cat.size")} placeholder={t("cat.size")} value={v.size} onChange={(e) => setVariant(i, "size", e.target.value)} />
              <Input aria-label={t("cat.color")} placeholder={t("cat.color")} value={v.color} onChange={(e) => setVariant(i, "color", e.target.value)} />
              <Input aria-label={t("cat.stock")} placeholder={t("cat.stock")} inputMode="numeric" value={v.stock} onChange={(e) => setVariant(i, "stock", e.target.value)} />
              <Input
                aria-label={t("cat.price_override")}
                placeholder={t("cat.price_override")}
                inputMode="numeric"
                value={v.price_override}
                onChange={(e) => setVariant(i, "price_override", e.target.value)}
              />
              <button type="button" aria-label={t("common.delete")} onClick={() => setD({ ...d, variants: d.variants.filter((_, j) => j !== i) })} className="rounded-lg p-2 text-slate-400 hover:bg-red-50 hover:text-red-600">
                ✕
              </button>
            </div>
          ))}
        </div>
        <Button type="button" size="sm" variant="ghost" className="mt-2" onClick={() => setD({ ...d, variants: [...d.variants, { size: "", color: "", stock: "", price_override: "" }] })}>
          + {t("cat.add_variant")}
        </Button>
      </div>
      <Textarea label={t("cat.images")} rows={2} value={d.images} onChange={(e) => setD({ ...d, images: e.target.value })} placeholder="https://…" />
      <Toggle checked={d.is_active} onChange={(v) => setD({ ...d, is_active: v })} label={t("cat.active")} />
      <ErrorBox error={save.error} />
      <div className="flex justify-end gap-2">
        <Button type="button" variant="secondary" onClick={onClose}>
          {t("common.cancel")}
        </Button>
        <Button type="submit" loading={save.isPending}>
          {t("common.save")}
        </Button>
      </div>
    </form>
  );
}

export function CatalogPage() {
  const { t, money } = useI18n();
  const qc = useQueryClient();
  const [q, setQ] = useState("");
  const [editing, setEditing] = useState<Draft | null>(null);
  const [importMsg, setImportMsg] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const products = useQuery({
    queryKey: ["products", q],
    queryFn: () => get<Product[]>(`/api/products?limit=200${q ? `&q=${encodeURIComponent(q)}` : ""}`),
  });
  const categories = useQuery({ queryKey: ["categories"], queryFn: () => get<Category[]>("/api/categories") });
  const remove = useMutation({
    mutationFn: (id: number) => del(`/api/products/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["products"] }),
  });
  const importFile = useMutation({
    mutationFn: (file: File) => {
      const fd = new FormData();
      fd.append("file", file);
      return api<{ created: number; updated: number; errors: string[] }>("/api/products/import", { method: "POST", body: fd });
    },
    onSuccess: (r) => {
      setImportMsg(t("cat.import_done", { created: r.created, updated: r.updated }) + (r.errors.length ? ` · ${r.errors.join("; ")}` : ""));
      qc.invalidateQueries({ queryKey: ["products"] });
      qc.invalidateQueries({ queryKey: ["categories"] });
    },
  });
  const cats = categories.data ?? [];

  return (
    <>
      <PageHeader
        title={t("cat.title")}
        actions={
          <>
            <a href="/api/products-import-template" className="inline-flex items-center rounded-lg px-3 py-2 text-sm font-semibold text-brand-700 hover:bg-brand-50">
              ⬇ {t("cat.template")}
            </a>
            <input
              ref={fileRef}
              type="file"
              accept=".xlsx,.csv"
              className="hidden"
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) importFile.mutate(f);
                e.target.value = "";
              }}
            />
            <Button variant="secondary" onClick={() => fileRef.current?.click()} loading={importFile.isPending}>
              {t("cat.import")}
            </Button>
            <Button onClick={() => setEditing(emptyDraft())}>+ {t("cat.add")}</Button>
          </>
        }
      />
      {importMsg && <p className="mb-4 rounded-lg bg-emerald-50 px-3 py-2.5 text-sm text-emerald-800 ring-1 ring-emerald-200">{importMsg}</p>}
      <ErrorBox error={products.error ?? importFile.error ?? remove.error} />
      <Input placeholder={t("common.search")} value={q} onChange={(e) => setQ(e.target.value)} className="mb-4 max-w-sm" />
      {products.isLoading ? (
        <Loading />
      ) : products.data?.length ? (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {products.data.map((p) => {
            const stock = p.variants.some((v) => v.stock == null) ? null : p.variants.reduce((s, v) => s + (v.stock ?? 0), 0);
            return (
              <Card key={p.id} className="flex flex-col">
                <div className="flex gap-3">
                  {p.images[0] ? (
                    <img src={p.images[0].url} alt="" className="h-16 w-16 shrink-0 rounded-lg bg-slate-100 object-cover" />
                  ) : (
                    <div className="flex h-16 w-16 shrink-0 items-center justify-center rounded-lg bg-cream text-2xl">📦</div>
                  )}
                  <div className="min-w-0">
                    <p className="truncate font-semibold text-slate-900">{p.name}</p>
                    <p className="text-sm font-medium text-brand-700">{money(p.price)}</p>
                    <div className="mt-1 flex flex-wrap gap-1">
                      {!p.is_active && <Badge tone="red">{t("cat.inactive")}</Badge>}
                      {cats.find((c) => c.id === p.category_id) && <Badge>{cats.find((c) => c.id === p.category_id)!.name}</Badge>}
                    </div>
                  </div>
                </div>
                <p className="mt-3 text-xs text-slate-500">
                  {p.variants
                    .map((v) => Object.values(v.attrs).join(" "))
                    .filter(Boolean)
                    .join(" · ") || "—"}
                </p>
                <p className="mt-1 text-xs text-slate-500">
                  {t("cat.stock_total")}: {stock == null ? t("cat.unlimited") : stock}
                </p>
                <div className="mt-auto flex gap-2 pt-4">
                  <Button size="sm" variant="secondary" onClick={() => setEditing(toDraft(p, cats))}>
                    {t("common.edit")}
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => window.confirm(t("cat.confirm_delete")) && remove.mutate(p.id)}>
                    {t("common.delete")}
                  </Button>
                </div>
              </Card>
            );
          })}
        </div>
      ) : (
        <Empty />
      )}
      <Modal open={!!editing} onClose={() => setEditing(null)} title={editing?.id ? editing.name : t("cat.new")}>
        {editing && <ProductEditor draft={editing} categories={cats} onClose={() => setEditing(null)} />}
      </Modal>
    </>
  );
}
