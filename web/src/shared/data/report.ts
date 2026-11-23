import { useCallback, useEffect, useState } from "react";

export interface Metrics {
  value_share: number;
  value_share_by_seed: number[];
  value_captured_eur_per_week: number;
  value_at_stake_eur_per_week: number;
  card_value_share: number;
  recall_by_card: number;
  material_pairs: number;
  cards_per_week: number;
  precision: number | null;
  duplicate_cards: number;
  false_cards: number;
  false_causes: Record<string, number>;
  unreviewed_cards: number;
  lead_median_h: number | null;
  decision_median_h: number | null;
  decision_p90_h: number | null;
  minutes_per_week: number;
  minutes_by_kind_per_week: Record<string, number>;
  cost_eur_per_week: number;
  cost_per_accepted_card_eur: number | null;
  model_calls_per_message: number;
  messages_per_week: number;
  holds_per_week: number;
  suppressed: number;
  suppressed_material: number;
  injection_cards: number;
  namesake_cards: number;
  wrong_entity_cards: number;
  rumour_cards: number;
}

export interface Design {
  label: string;
  kind: string;
  model: string | null;
  metrics: Metrics;
}

export interface Diff {
  diff: number;
  lo: number;
  hi: number;
  clusters: number;
}

export interface Gate {
  gate: string;
  value: number | null;
  limit: number;
  kind: "min" | "max";
  pass: boolean;
}

export interface TraceStep {
  step: string;
  [key: string]: unknown;
}

export interface CardView {
  card_id: string;
  category: string;
  kind: string;
  driver: string;
  impact_eur: number;
  lever: string;
  path: string[];
  evidence: { msg_id: string; quote: string }[];
  sources: { msg_id: string; source: string; headline: string; published_h: number }[];
  created_h: number;
  decision: { decision: string; reason: string | null; at_h: number } | null;
  truth: { material: boolean; true_impact_eur: number | null; right_lever: string | null };
  trace: TraceStep[];
}

export interface MessageView {
  msg_id: string;
  note: string;
  headline: string;
  body: string;
  source: string;
  outcome: string | null;
  reason: string | null;
  trace: TraceStep[];
}

export interface SplitReport {
  split: string;
  variant: string;
  seeds: number[];
  designs: Record<string, Design>;
  order: string[];
  ablations: string[];
  model_swap: string[];
  comparisons: Record<string, Diff>;
  by_kind: Record<string, Record<string, { value_share: number; pairs: number; caught_by_card: number }>>;
  weeks: Record<string, { week: number; at_stake_eur: number; captured_eur: number; cards: number }[]>;
  samples: { cards: Record<string, CardView>; messages: Record<string, MessageView> };
  graph: { categories: number; suppliers: number; contracts: number; tier2_disclosed: number; tier2_true: number; edges: Record<string, number> };
  gates: {
    platform: Gate[];
    platform_pass: boolean;
    model_swap: Record<string, { value_share_below_platform_pts: number; precision: number | null; minutes_ratio_to_platform: number; verdict: string }>;
  };
}

export interface Report {
  dev: SplitReport;
  heldout?: SplitReport | null;
}

export type Load = { state: "loading" } | { state: "error"; message: string } | { state: "ready"; report: Report };

export function useReport(url = "data/report.json"): [Load, () => void] {
  const [load, setLoad] = useState<Load>({ state: "loading" });
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let live = true;
    setLoad({ state: "loading" });
    fetch(url)
      .then((r) => {
        if (!r.ok) throw new Error(`The report did not load (HTTP ${r.status}).`);
        return r.json() as Promise<Report>;
      })
      .then((report) => {
        if (!report || !report.dev) throw new Error("The report file has no development results.");
        if (live) setLoad({ state: "ready", report });
      })
      .catch((e: unknown) => live && setLoad({ state: "error", message: e instanceof Error ? e.message : "The report did not load." }));
    return () => {
      live = false;
    };
  }, [url, attempt]);
  const retry = useCallback(() => setAttempt((a) => a + 1), []);
  return [load, retry];
}
