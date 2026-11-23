import type { Transition } from "framer-motion";

/** One easing for the console: quick out, settled in. */
export const settle: Transition = { type: "tween", ease: [0.2, 0.7, 0.2, 1], duration: 0.32 };

/** The walk from a signal to money draws in step by step, once. */
export const stepIn = (i: number): Transition => ({ ...settle, delay: 0.15 + i * 0.12 });
