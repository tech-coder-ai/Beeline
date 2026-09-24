# drools-sql-equivalence

A Spring Boot 4 service that checks whether a **Drools rule's condition
logic** (the `when` block) and a **SQL / Spark SQL `WHERE` predicate**
express the same boolean logic — even when they're structured completely
differently (different order, `IN` vs `OR`-chain, `BETWEEN` vs two
comparisons, De Morgan/distributive rewrites, etc).

## How it works

Structural AST diffing doesn't work here: Drools (Rete pattern matching over
facts) and SQL (declarative relational algebra) have fundamentally different
execution models, so their parse trees never look alike even when the logic
is identical. Instead this lowers both into a common, execution-model-free
IR and compares *there*:

```
Drools "when" block --[DroolsRuleParser]--\
                                            >--> common Expr IR --[EquivalenceChecker]--> verdict
SQL "WHERE" clause  --[SqlWherePredicateParser]--/
```

- **`ir/`** — `Expr` (And/Or/Not/Comparison/BoolConst) and `Literal`
  (Number/String/Bool). Every `Comparison` is `field <op> constant`; there
  is no field-vs-field comparison in this grammar. That restriction is what
  makes the equivalence check below *exact*, not a heuristic.
- **`parser/`** — a single shared boolean-expression tokenizer/parser
  (`&&`/`AND`, `||`/`OR`, `!`/`NOT`, `==`/`=`, `IN`, `BETWEEN` all fold to
  the same tokens), plus two thin dialect-specific preprocessors:
  - `DroolsRuleParser` extracts the `when`/`then` block, strips bind
    variables (`$p :`) and pattern types (`Person(...)`), turns constraint
    commas into `&&` (Drools' native meaning), and ANDs pattern clauses
    together (or ORs one if prefixed with `or`). `eval(...)` clauses are
    parsed as a raw boolean expression.
  - `SqlWherePredicateParser` extracts the text after `WHERE` up to
    `GROUP BY`/`ORDER BY`/`HAVING`/`LIMIT`/etc. If no `WHERE` is found, the
    whole input is treated as a bare predicate.
- **`engine/`** — the actual equivalence check. `DomainBuilder` collects
  every constant each field is compared against and builds a finite
  **critical-value set** per field: for a numeric field with constants
  `{18, 65}` it tests `{17, 18, 41.5, 65, 66}` — every constant plus one
  probe point in each gap and beyond each end, which is exactly what's
  needed to distinguish every region `<`, `<=`, `=`, `>=`, `>` could carve
  out. `EquivalenceChecker` then evaluates both expressions over the
  Cartesian product of all fields' critical values. If every combination
  agrees, the two are **provably equivalent** for this grammar — not
  "no counterexample found," an actual proof, because nothing outside the
  critical-value set can flip either expression's answer. If the
  combination count is too large (capped at 200k), it falls back to 20k
  random samples from the same candidate sets and reports `mode: SAMPLED`
  instead of `EXACT`, honestly.

## Running it

```bash
mvn spring-boot:run
```

```bash
curl -s -X POST http://localhost:8085/api/v1/equivalence/check \
  -H "Content-Type: application/json" \
  -d '{
    "droolsRule": "rule \"Adults\" when $p : Person(age >= 18, status == \"ACTIVE\") then end",
    "sql": "SELECT * FROM person WHERE age >= 18 AND status = '\''ACTIVE'\''"
  }'
```

```json
{
  "equivalent": true,
  "mode": "EXACT",
  "casesChecked": 6,
  "normalizedDrools": "(age >= 18 AND status = 'ACTIVE')",
  "normalizedSql": "(age >= 18 AND status = 'ACTIVE')",
  "counterexamples": []
}
```

Flip `age >= 18` to `age > 18` on the SQL side and you get a false verdict
plus the exact counterexample where they diverge (`age = 18`).

## Scope and limitations (read before trusting a verdict)

This compares **filter-predicate logic only** — deliberately, because that
fragment is where exact equivalence checking is tractable without an SMT
solver. It does **not** attempt to model:

- **Joins, aggregates, `GROUP BY`/`HAVING`, subqueries, window functions** —
  these change what rows/columns a query *produces*, not just which facts a
  single predicate accepts. Comparing those needs a real relational-algebra
  IR (e.g. built on Apache Calcite or Spark's own Catalyst analyzer), which
  is a materially bigger project than this one.
- **Drools RHS ("then") side effects** — insertions, modifications, calls
  out to other services. Only the LHS condition is compared.
- **`exists`/`not`/`accumulate`/`from`, cross-fact joins in Drools** — out
  of scope; the parser will reject these with a clear error rather than
  silently mis-parsing them.
- **Field/column name reconciliation** — the tool assumes the Drools fact
  attribute and the SQL column refer to the same thing under the same name
  (matched case-insensitively). It does not know that `person.age` and
  `p_age` mean the same thing; that's a schema-mapping problem, not a logic
  one, and is left to the caller (alias your SQL columns to match).
- **String fields compared with `<`/`<=`/`>`/`>=`** — the critical-value set
  for strings only guarantees exactness for `=`/`!=`/`IN` usage (by far the
  common case for status/category fields). Lexicographic ordering on
  strings isn't covered.

If you need to go further — true cross-field constraints, full SQL query
equivalence including joins, or a formally verified proof rather than a
critical-value enumeration — the natural next step is embedding an SMT
solver (Z3) over the same `Expr` IR, or lowering to Datalog and using a
solver built for that.
