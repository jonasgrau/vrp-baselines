# vrp-baselines

Solve CVRPLIB instances with three standard baselines and report the gap to the
best known solution (BKS). Every cost is recomputed and every solution checked by
[routeviz](https://github.com/jonasgrau/routeviz), never taken from the solver.

| Method | What it is |
|---|---|
| `savings` | Clarke & Wright (1964) savings + 2-opt. Deterministic, milliseconds. |
| `ortools` | Google OR-Tools routing: savings start, guided local search. |
| `hgs` | Hybrid Genetic Search ([Vidal 2022](https://github.com/vidalt/HGS-CVRP)), state of the art. |

## Usage

```bash
pip install "vrp-baselines[hgs] @ git+https://github.com/jonasgrau/vrp-baselines"

vrp-baselines solve X-n101-k25.vrp -m hgs -t 10       # writes X-n101-k25.hgs.sol
vrp-baselines bench instances/*.vrp -t 10 --seeds 1-5 --csv runs.csv --sol-dir sols/
```

The BKS is read from `<instance>.sol` next to the instance, as CVRPLIB ships them.
Supports capacity and route-length limits (`DISTANCE`, `SERVICE_TIME`).
`hgs` needs a C++ compiler and CMake to install.

## Results

Gap to BKS, 10 s per run, single thread (Xeon 2.1 GHz). HGS: mean over 5 seeds,
best in brackets. The other two ignore the seed and run once (OR-Tools under a
time limit can vary with machine speed; repeated runs here gave identical results).

| Instance | BKS | savings | ortools | hgs |
|---|---:|---:|---:|---:|
| A-n32-k5 | 784 | 5.74 % | 0.00 % | 0.00 % (0.00) |
| B-n31-k5 | 672 | 0.74 % | 0.00 % | 0.00 % (0.00) |
| CMT6 | 555.43 | 11.34 % | 0.64 % | 0.00 % (0.00) |
| F-n72-k4 | 237 | 6.75 % | 2.53 % | 0.00 % (0.00) |
| Golden_1 | 5,623.47 | 8.17 % | 2.70 % | 0.28 % (0.19) |
| Li_21 | 16,212.83 | 14.78 % | 11.68 % | 0.06 % (0.02) |
| M-n101-k10 | 820 | 0.98 % | 0.98 % | 0.00 % (0.00) |
| P-n16-k8 | 450 | 7.11 % | 0.00 % | 0.00 % (0.00) |
| Tai75a | 1,618.36 | 1.57 % | 0.27 % | 0.00 % (0.00) |
| X-n101-k25 | 27,591 | 4.87 % | 5.42 % | 0.00 % (0.00) |
| **mean** | | **6.21 %** | **2.42 %** | **0.03 %** |

Reading it fairly: the instances are small (15–560 customers) and 10 s is a short
budget, so this shows the ranking at a fixed small budget, not each method's
limit. OR-Tools' configuration was chosen on a pilot run on M-n101-k10 and
X-n101-k25 and then fixed for all instances. Fleet size is not constrained.

Reproduce: `vrp-baselines bench instances/*.vrp -t 10 --seeds 1-5`

MIT licensed · `pip install -e ".[hgs,dev]" && pytest` · Instances: see [`instances/`](instances/)
