# Spec: <mod>  (step <n>, #65)
Status: draft | reviewed (leak reviewer, date) | frozen. Writer: <model>, <date>.
Rules: docs/cleanroom.md "Spec format". No pseudo-C, no SDK names, no copied comments. Lint: `cleanroom_lint.py --tree specs`.

## 1. Interface
- Header(s): `awto/include/<x>.h`. Per function: arguments (units, ranges), return value, side effects, context (main / ISR).

## 2. Register sequences
| # | reg | mask | value | condition | wait |
|---|---|---|---|---|---|
| S1 | `OUR_NAME` / `P31_A0` | 0x80 | 1 | always | - |

## 3. Barriers and commutative groups
- Group G1 = {S2..S5}: any order. Barrier S6 after G1, before S7.

## 4. Timing
| what | min / max | source | tag |
|---|---|---|---|

## 5. Decision tables / state machines

## 6. Data
Tags: `derived` / `measured` / `sdk-value` (Realtek SDK source default) / `dahua-value` (original Dahua firmware dump, RE or RTDCustomerTool board data).
| name | value | unit | tag (derived / measured / sdk-value / dahua-value) | source |
|---|---|---|---|---|

## 7. Oracle
- Vectors: `specs/vectors/<mod>.tsv` (format line 1).
- Bus sequences: the tables in 2; host test must reproduce them with a recording `REG8` mock.
- Trace: `specs/<mod>.equiv` with `trace_equiv.py` (mode list).
- Sim / hardware checks.

## 8. Implementer task
- Files: `awto/<mod>/*.c`, `tests/host/test_<mod>.c`.
- Required functions; budget (code bytes, cycles); forbidden: anything not in this brief.

## 9. Q&A
