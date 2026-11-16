"""Run the whole pipeline in order with one command:  python src/run_all.py"""
# STEP 1: Imports
from __future__ import annotations

import argparse
import sys
import time

import biobanking_check
import clean
import export_powerbi
import gap_analysis
import make_charts
import price_model
import price_trends
from common import PipelineError, get_logger

log = get_logger("run_all")

STEPS = [
    ("Clean the registers", clean.main),
    ("Gap analysis", gap_analysis.main),
    ("Price trends", price_trends.main),
    ("BioBanking cross-check", biobanking_check.main),
    ("Power BI export", export_powerbi.main),
    ("Charts", make_charts.main),
    ("Price model (regression + machine learning)", price_model.main),
]


# STEP 2: Run each step, stop with a clear message if one fails
def main(skip_charts: bool = False) -> int:
    start = time.time()
    for number, (name, step) in enumerate(STEPS, 1):
        if skip_charts and step is make_charts.main:
            log.info("[%d/%d] %s: skipped", number, len(STEPS), name)
            continue
        log.info("[%d/%d] %s", number, len(STEPS), name)
        try:
            step()
        except PipelineError as exc:
            log.error("Pipeline stopped at '%s':\n%s", name, exc)
            return 1
    log.info("Done in %.0f seconds.", time.time() - start)
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-charts", action="store_true", help="don't redraw the charts")
    sys.exit(main(parser.parse_args().skip_charts))
