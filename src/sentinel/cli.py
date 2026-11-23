"""python -m sentinel.cli run dev | run heldout | gate dev | report | serve"""

from __future__ import annotations

import argparse
import json
import sys

from . import config
from .lab import report, study


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="sentinel")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="run every design on a split")
    r.add_argument("split", choices=["dev", "heldout"])
    g = sub.add_parser("gate", help="exit 1 if the sentinel fails a gate on a split")
    g.add_argument("split", choices=["dev", "heldout"])
    sub.add_parser("report", help="regenerate REPORT.md, the README block and the dashboard data")
    s = sub.add_parser("serve", help="run the API on a simulated feed")
    s.add_argument("--port", type=int, default=8000)
    args = p.parse_args(argv)

    if args.cmd == "run":
        if args.split == "heldout":
            try:
                res = study.run_heldout_once()
            except study.HeldOutLocked as e:
                print(e, file=sys.stderr)
                return 3
        else:
            res = study.run_split("dev")
            study.write("dev", res)
        m = res["designs"]["platform"]["metrics"]
        print(f"{args.split}: value captured {m['value_share']:.3f}, cards that mattered {m['precision']:.3f}, gates pass: {res['gates']['platform_pass']}")
        return 0
    if args.cmd == "gate":
        res = json.loads((config.REPORTS / f"{args.split}.json").read_text(encoding="utf-8"))
        for x in res["gates"]["platform"]:
            print(f"{'pass' if x['pass'] else 'FAIL'}  {x['gate']}: {x['value']} (limit {x['limit']})")
        return 0 if res["gates"]["platform_pass"] else 1
    if args.cmd == "report":
        for path in report.write_all():
            print(f"wrote {path.relative_to(config.ROOT)}")
        return 0
    if args.cmd == "serve":
        import uvicorn

        from .service.demo import create_demo_app

        uvicorn.run(create_demo_app(), host="127.0.0.1", port=args.port)
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
