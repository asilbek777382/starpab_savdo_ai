import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { get, put } from "./api";
import type { Settings } from "./types";

/** Sozlamalar bitta obyekt: sahifa o'z qismini o'zgartiradi, butun obyekt PUT qilinadi. */
export function useSettings() {
  const qc = useQueryClient();
  const query = useQuery({ queryKey: ["settings"], queryFn: () => get<Settings>("/api/settings") });
  const save = useMutation({
    mutationFn: (patch: Partial<Settings>) => put<Settings>("/api/settings", { ...query.data, ...patch }),
    onSuccess: (data) => qc.setQueryData(["settings"], data),
  });
  return { query, save };
}
