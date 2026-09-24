import { useEffect, useState, type FormEvent } from "react";
import { useI18n } from "../i18n";
import type { Settings } from "../types";
import { Button, Card, cx, ErrorBox, Input, Loading, PageHeader, SavedFlash, Select, Textarea, Toggle } from "../ui";
import { useSettings } from "../useSettings";

export function AiSettingsPage() {
  const { t } = useI18n();
  const { query, save } = useSettings();
  const [s, setS] = useState<Settings | null>(null);
  const [keywords, setKeywords] = useState("");
  useEffect(() => {
    if (query.data) {
      setS(query.data);
      setKeywords(query.data.handoff_rules.keywords.join(", "));
    }
  }, [query.data]);
  if (!s) return query.error ? <ErrorBox error={query.error} /> : <Loading />;
  const rules = s.handoff_rules;
  const submit = (e: FormEvent) => {
    e.preventDefault();
    save.mutate({
      ...s,
      handoff_rules: {
        ...rules,
        keywords: keywords
          .split(",")
          .map((k) => k.trim())
          .filter(Boolean),
      },
    });
  };
  return (
    <form onSubmit={submit}>
      <PageHeader
        title={t("ai.title")}
        actions={
          <div className="flex items-center gap-3">
            <SavedFlash show={save.isSuccess && !save.isPending} />
            <Button type="submit" loading={save.isPending}>
              {t("common.save")}
            </Button>
          </div>
        }
      />
      <ErrorBox error={save.error} />
      <div className="space-y-6">
        <Card>
          <Toggle checked={s.ai_enabled} onChange={(v) => setS({ ...s, ai_enabled: v })} label={t("ai.enabled")} hint={t("ai.enabled_hint")} />
        </Card>
        <Card title={t("ai.mode")}>
          <div className="grid gap-3 sm:grid-cols-2" role="radiogroup" aria-label={t("ai.mode")}>
            {(["sell", "lead"] as const).map((mode) => (
              <button
                type="button"
                role="radio"
                aria-checked={s.ai_mode === mode}
                key={mode}
                onClick={() => setS({ ...s, ai_mode: mode })}
                className={cx(
                  "rounded-xl p-4 text-left ring-2 transition",
                  s.ai_mode === mode ? "bg-brand-50 ring-brand-500" : "bg-white ring-slate-200 hover:ring-slate-300",
                )}
              >
                <p className="font-semibold text-brand-900">
                  {mode === "sell" ? "🛒" : "📞"} {t(`ai.mode.${mode}`)}
                </p>
                <p className="mt-1 text-sm text-slate-600">{t(`ai.mode.${mode}_hint`)}</p>
              </button>
            ))}
          </div>
          {s.ai_mode === "lead" && (
            <div className="mt-4 space-y-3">
              <Toggle checked={s.handoff_after_lead} onChange={(v) => setS({ ...s, handoff_after_lead: v })} label={t("ai.handoff_after_lead")} />
              <div className="rounded-lg bg-slate-50 px-3 py-2.5 text-sm text-slate-600">
                {s.lead_chat_id ? (
                  <span className="flex flex-wrap items-center gap-2">
                    {t("ai.lead_group", { id: s.lead_chat_id })}
                    <Button type="button" size="sm" variant="ghost" onClick={() => setS({ ...s, lead_chat_id: null })}>
                      {t("ai.lead_group_reset")}
                    </Button>
                  </span>
                ) : (
                  t("ai.lead_group_none")
                )}
              </div>
            </div>
          )}
        </Card>
        <Card title={t("ai.voice")}>
          <p className="mb-4 text-sm text-slate-600">{t("ai.voice_hint")}</p>
          {!s.voice_available && <p className="mb-4 rounded-lg bg-amber-50 px-3 py-2.5 text-sm text-amber-900 ring-1 ring-amber-200">{t("ai.voice_unavailable")}</p>}
          <div className="flex flex-wrap gap-2" role="radiogroup" aria-label={t("ai.voice")}>
            {(["off", "on_voice", "always"] as const).map((mode) => (
              <button
                type="button"
                role="radio"
                key={mode}
                aria-checked={s.voice_mode === mode}
                disabled={!s.voice_available && mode !== "off"}
                onClick={() => setS({ ...s, voice_mode: mode })}
                className={cx(
                  "rounded-full px-4 py-2 text-sm font-medium ring-1 transition disabled:cursor-not-allowed disabled:opacity-50",
                  s.voice_mode === mode ? "bg-brand-700 text-white ring-brand-700" : "bg-white text-slate-700 ring-slate-200 hover:ring-brand-500",
                )}
              >
                {t(`ai.voice.${mode}`)}
              </button>
            ))}
          </div>
          {s.voice_mode !== "off" && (
            <div className="mt-4 max-w-xs">
              <Select label={t("ai.voice_gender")} value={s.voice_gender} onChange={(e) => setS({ ...s, voice_gender: e.target.value as Settings["voice_gender"] })}>
                <option value="female">{t("ai.voice.female")}</option>
                <option value="male">{t("ai.voice.male")}</option>
              </Select>
            </div>
          )}
        </Card>
        <Card>
          <div className="space-y-5">
            <Textarea label={t("ai.tasks")} hint={t("ai.tasks_hint")} rows={5} value={s.ai_tasks} onChange={(e) => setS({ ...s, ai_tasks: e.target.value })} maxLength={4000} />
            <Textarea label={t("ai.rules")} hint={t("ai.rules_hint")} rows={4} value={s.rules_text} onChange={(e) => setS({ ...s, rules_text: e.target.value })} />
            <Select label={t("ai.tone")} value={s.tone} onChange={(e) => setS({ ...s, tone: e.target.value })}>
              {(["friendly", "formal", "casual"] as const).map((tone) => (
                <option key={tone} value={tone}>
                  {t(`ai.tone.${tone}`)}
                </option>
              ))}
            </Select>
          </div>
        </Card>
        <Card title="🙋">
          <div className="space-y-5">
            <Toggle checked={rules.allow_discounts} onChange={(v) => setS({ ...s, handoff_rules: { ...rules, allow_discounts: v } })} label={t("ai.discounts")} />
            <div className="grid gap-4 sm:grid-cols-2">
              <Input
                label={t("ai.silence")}
                type="number"
                min={1}
                max={1440}
                value={rules.silence_minutes}
                onChange={(e) => setS({ ...s, handoff_rules: { ...rules, silence_minutes: Number(e.target.value) } })}
              />
              <Input
                label={t("ai.handoff_hours")}
                type="number"
                min={0.5}
                max={72}
                step={0.5}
                value={rules.handoff_hours}
                onChange={(e) => setS({ ...s, handoff_rules: { ...rules, handoff_hours: Number(e.target.value) } })}
              />
            </div>
            <Input label={t("ai.keywords")} value={keywords} onChange={(e) => setKeywords(e.target.value)} placeholder="admin, direktor" />
          </div>
        </Card>
      </div>
    </form>
  );
}
