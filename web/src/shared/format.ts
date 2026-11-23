export const pct = (x: number | null | undefined, d = 1): string => (x === null || x === undefined ? "n/a" : `${(x * 100).toFixed(d)}%`);

export const pts = (x: number): string => `${x >= 0 ? "+" : "−"}${Math.abs(x * 100).toFixed(1)}`;

export function eur(x: number | null | undefined): string {
  if (x === null || x === undefined) return "n/a";
  const a = Math.abs(x);
  const sign = x < 0 ? "−" : "";
  if (a >= 1e6) return `${sign}€${(a / 1e6).toFixed(2)}M`;
  if (a >= 1e3) return `${sign}€${Math.round(a / 1e3).toLocaleString("en-GB")}k`;
  return `${sign}€${a.toFixed(3)}`;
}

export const hours = (x: number | null | undefined): string => (x === null || x === undefined ? "n/a" : `${x.toFixed(1)} h`);

export const LEVERS: Record<string, string> = {
  index_pass_through_check: "Check the index pass-through",
  renewal_should_cost: "Prepare the renewal with a should-cost",
  shift_volume: "Shift volume to an alternate supplier",
  landed_cost_requote: "Re-quote the landed cost",
  stop_new_pos: "Stop new purchase orders; legal review",
  corrective_action_plan: "Ask for a corrective action plan",
  dual_source_buffer: "Secure buffer stock and a second source",
  qualify_alternate: "Qualify an alternate supplier",
  review: "Manager decides",
};

export const CAUSES: Record<string, string> = {
  injection: "An instruction hidden in the article",
  namesake: "A namesake, not our supplier",
  rumour: "A rumour that died",
  below_tolerance: "Real, but within the category's tolerance",
  wrong_entity: "The wrong supplier",
  noise: "Nothing we buy",
  estimate_or_read: "A misread amount",
};
