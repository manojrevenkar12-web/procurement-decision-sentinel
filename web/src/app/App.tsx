import { AnimatePresence, motion } from "framer-motion";
import { useState } from "react";
import { Docket } from "../features/docket/Docket";
import { Ablations } from "../features/results/Ablations";
import { Comparison } from "../features/results/Comparison";
import { FalseCards } from "../features/results/FalseCards";
import { Gates } from "../features/results/Gates";
import { Stopped } from "../features/stopped/Stopped";
import { useReport, type SplitReport } from "../shared/data/report";
import { eur, pct } from "../shared/format";
import { settle } from "../shared/theme/motion";
import { ThemeToggle } from "../shared/theme/ThemeToggle";
import controls from "../shared/ui/controls.module.css";
import { Empty, ErrorState, Loading } from "../shared/ui/states";
import styles from "./App.module.css";

type Split = "dev" | "heldout";

function KeyNumbers({ res }: { res: SplitReport }) {
  const p = res.designs.platform!.metrics;
  const s = res.designs.status_quo!.metrics;
  return (
    <aside className={styles.numbers} aria-label="This run in four numbers">
      <div>
        <p className={styles.big}>{pct(p.value_share, 0)}</p>
        <p>of the mitigable money was acted on in time, against {pct(s.value_share, 0)} with an analyst reading the feed.</p>
      </div>
      <div>
        <p className={styles.big}>{pct(p.precision, 0)}</p>
        <p>of the cards mattered. The analyst's cards: {pct(s.precision, 0)}.</p>
      </div>
      <div>
        <p className={styles.big}>{Math.round(p.minutes_per_week)} min</p>
        <p>of people's time a week, against {Math.round(s.minutes_per_week)} min.</p>
      </div>
      <div>
        <p className={styles.big}>{eur(p.cost_per_accepted_card_eur)}</p>
        <p>of model cost for each card a manager accepted.</p>
      </div>
    </aside>
  );
}

function Body({ res }: { res: SplitReport }) {
  return (
    <>
      <section className={styles.hero} aria-labelledby="hero-title">
        <div className={styles.heroText}>
          <h2 id="hero-title">A news line becomes a decision, with the money and the reason attached</h2>
          <p>
            The model only reads the article. Code checks every quote, finds the supplier by legal form and country, walks the buyer's contracts and sub-supplier links to a yearly amount, and shows a card only when it clears €150k and no manager has already called it noise.
          </p>
        </div>
        <Docket cards={res.samples.cards} />
        <KeyNumbers res={res} />
      </section>

      <section className={styles.section} aria-labelledby="designs-title">
        <h2 id="designs-title">Three ways to watch the market</h2>
        <p className={styles.lead}>The monthly category review runs in every design. Value decays over each signal's horizon, and a wrong lever captures half.</p>
        <Comparison res={res} />
      </section>

      <section className={styles.section} aria-labelledby="gates-title">
        <h2 id="gates-title">Gates</h2>
        <p className={styles.lead}>Set on the development seeds before the held-out run, and never loosened after it.</p>
        <Gates res={res} />
      </section>

      <section className={styles.section} aria-labelledby="false-title">
        <h2 id="false-title">Cards that did not matter, and why</h2>
        <FalseCards res={res} />
      </section>

      <section className={styles.section} aria-labelledby="ablations-title">
        <h2 id="ablations-title">One switch at a time</h2>
        <p className={styles.lead}>Each row turns one part of the sentinel off on the same world and luck. The dot is the difference in value captured; the line is its 95% interval over events.</p>
        <Ablations res={res} />
      </section>

      <section className={styles.section} aria-labelledby="stopped-title">
        <h2 id="stopped-title">Stopped before a card</h2>
        <Stopped messages={res.samples.messages} />
      </section>
    </>
  );
}


export function App() {
  const [load, retry] = useReport();
  const [split, setSplit] = useState<Split>("dev");
  const res = load.state === "ready" ? (split === "dev" ? load.report.dev : load.report.heldout ?? null) : null;
  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <div>
          <h1 className={styles.title}>Procurement decision sentinel</h1>
          <p className={styles.tagline}>Commodity, tariff and supplier signals, turned into the few decisions that matter</p>
        </div>
        <div className={styles.controls}>
          <div className={controls.segmented} role="group" aria-label="Which seeds">
            <button type="button" className={controls.segment} aria-pressed={split === "dev"} onClick={() => setSplit("dev")}>
              Development seeds
            </button>
            <button type="button" className={controls.segment} aria-pressed={split === "heldout"} onClick={() => setSplit("heldout")}>
              Held-out seeds, run once
            </button>
          </div>
          <ThemeToggle />
        </div>
      </header>
      <main className={styles.main}>
        {load.state === "loading" && <Loading label="Loading the report" />}
        {load.state === "error" && <ErrorState message={load.message} onRetry={retry} />}
        {load.state === "ready" && !res && (
          <Empty title="The held-out seeds have not been run">
            Run <code>python -m sentinel.cli run heldout</code> once. It writes a lock first, so it cannot run twice.
          </Empty>
        )}
        <AnimatePresence mode="wait">
          {res && (
            <motion.div key={split} className={styles.stack} initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={settle}>
              <Body res={res} />
            </motion.div>
          )}
        </AnimatePresence>
      </main>
      <footer className={styles.footer}>
        <p>
          Everything here is simulated: the buyer, its suppliers, the news and the model's mistakes. The README's Limits section says what that leaves out.
        </p>
      </footer>
    </div>
  );
}
