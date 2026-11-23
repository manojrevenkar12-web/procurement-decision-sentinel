import { motion, useReducedMotion } from "framer-motion";
import { useState } from "react";
import type { CardView, TraceStep } from "../../shared/data/report";
import { LEVERS, eur } from "../../shared/format";
import { stepIn } from "../../shared/theme/motion";
import { Empty } from "../../shared/ui/states";
import styles from "./docket.module.css";

const TABS: Record<string, string> = {
  tier2_tariff: "Tariff, through a sub-supplier",
  supplier_event: "Supplier in trouble",
  commodity_move: "Commodity price move",
};

function stepText(t: TraceStep): string {
  switch (t.step) {
    case "read":
      return t.resumed ? "Read: resumed from the journal, no second model call" : `Read by ${String(t.model)}: ${String(t.tokens_in)} tokens in (${String(t.tokens_cached)} cached), ${String(t.tokens_out)} out, €${Number(t.cost_eur).toFixed(4)}`;
    case "check":
      return `Quotes checked: ${String(t.reason)}${(t.dropped as string[] | undefined)?.length ? `; dropped ${(t.dropped as string[]).join(", ")}` : ""}${t.instruction_like ? "; the article contains an instruction to machines" : ""}`;
    case "resolve":
      return `Supplier: ${String(t.reason)}`;
    case "graph":
      return `Graph walk: ${String(t.exposures)} categories exposed, ${String(t.below_materiality)} below €150k, ${(t.cards as string[]).length} card(s)`;
    case "merge":
      return `Same facts as an earlier article: linked to ${String(t.cards_linked)} card(s)`;
    case "copy_check":
      return `Syndicated copy of ${String(t.copy_of)} (${Math.round(Number(t.similarity) * 100)}% the same words): no model call`;
    case "status":
      return "Unconfirmed: watched until confirmed or withdrawn";
    case "hold":
      return `Held for the market desk: ${String(t.reason)}`;
    case "desk":
      return t.resolved ? "Market desk read it and gave the facts" : "Market desk: nothing for us";
    case "crash":
      return `Worker stopped after the ${String(t.after)} step; the broker delivered it again`;
    default:
      return t.step;
  }
}

export function Trace({ steps }: { steps: TraceStep[] }) {
  if (!steps.length) return <p className={styles.muted}>No trace was kept for this article.</p>;
  return (
    <ol className={styles.trace}>
      {steps.map((t, i) => (
        <li key={i}>{stepText(t)}</li>
      ))}
    </ol>
  );
}

export function Docket({ cards }: { cards: Record<string, CardView> }) {
  const keys = Object.keys(TABS).filter((k) => cards[k]);
  const [active, setActive] = useState(keys[0] ?? "");
  const reduce = useReducedMotion();
  const card = cards[active];
  if (!card) return <Empty title="No sample card in this run">The study keeps sample cards from the first seed. Run the study again to write them.</Empty>;
  const priceKind = card.kind !== "supplier_event";
  const tone = priceKind && card.impact_eur < 0 ? styles.saving : styles.cost;
  const decided = card.decision;
  return (
    <article className={styles.docket} aria-labelledby="docket-title">
      <div role="tablist" aria-label="Sample cards" className={styles.tabs}>
        {keys.map((k) => (
          <button key={k} id={`tab-${k}`} role="tab" type="button" aria-selected={k === active} aria-controls="docket-panel" className={styles.tab} onClick={() => setActive(k)}>
            {TABS[k]}
          </button>
        ))}
      </div>
      <div id="docket-panel" role="tabpanel" aria-labelledby={`tab-${active}`} className={styles.body}>
        <header className={styles.head}>
          <h3 id="docket-title">{card.category}</h3>
          <p className={`${styles.amount} ${tone}`}>
            {eur(card.impact_eur)}
            <span className={styles.per}>a year{priceKind ? (card.impact_eur < 0 ? ", lower cost" : ", higher cost") : " at risk"}</span>
          </p>
          <p className={styles.lever}>{LEVERS[card.lever] ?? card.lever}</p>
        </header>
        <ol className={styles.path} aria-label="Why this card exists" key={active}>
          {card.path.map((p, i) => (
            <motion.li key={i} className={i === card.path.length - 1 ? styles.total : undefined} initial={reduce ? false : { opacity: 0, x: -8 }} animate={{ opacity: 1, x: 0 }} transition={stepIn(i)}>
              {p}
            </motion.li>
          ))}
        </ol>
        <div className={styles.evidence}>
          {card.evidence.slice(0, 2).map((e) => (
            <blockquote key={e.msg_id + e.quote}>
              <p>{e.quote}</p>
              <footer>{card.sources.find((s) => s.msg_id === e.msg_id)?.source ?? e.msg_id}</footer>
            </blockquote>
          ))}
          {card.sources.length > 1 && <p className={styles.muted}>{card.sources.length - 1} more article(s) reported the same facts and were linked, not carded again.</p>}
        </div>
        <dl className={styles.outcome}>
          <div>
            <dt>Manager</dt>
            <dd>{decided ? (decided.decision === "accept" ? "Accepted" : `Dismissed (${decided.reason?.replace("_", " ")})`) : "Not reviewed"}</dd>
          </div>
          <div>
            <dt>What was true</dt>
            <dd>
              {card.truth.material ? "It mattered" : "It did not matter"}; true impact {eur(card.truth.true_impact_eur)}
            </dd>
          </div>
        </dl>
        <details className={styles.details}>
          <summary>How the sentinel handled the article</summary>
          <Trace steps={card.trace} />
        </details>
      </div>
    </article>
  );
}
