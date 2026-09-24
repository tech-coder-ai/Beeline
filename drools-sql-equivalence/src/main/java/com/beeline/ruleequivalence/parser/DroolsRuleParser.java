package com.beeline.ruleequivalence.parser;

import com.beeline.ruleequivalence.ir.Expr;

import java.util.ArrayList;
import java.util.List;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Lowers a Drools rule's LHS ("when" block) into the common {@link Expr} IR.
 * Supported shape, which covers the common case of stateless condition
 * rules:
 *
 * <pre>
 * when
 *     $p : Person(age >= 18, status == "ACTIVE")
 *     Account(balance > 1000 || balance < -500)
 * then
 *     ...
 * end
 * </pre>
 *
 * Rules:
 * <ul>
 *   <li>Multiple pattern clauses are AND-ed together unless a clause is
 *       explicitly prefixed with {@code or}.</li>
 *   <li>Commas inside a single pattern's constraints are AND (Drools'
 *       native meaning).</li>
 *   <li>An optional bind variable ({@code $p :}) before a pattern is
 *       ignored -- only the constraint logic is compared.</li>
 *   <li>{@code eval(...)} clauses are parsed as a raw boolean expression.</li>
 * </ul>
 * Out of scope: {@code exists}/{@code not}/{@code accumulate}/{@code from},
 * cross-fact joins, and anything in the RHS ("then") -- this tool compares
 * condition logic only, not side effects.
 */
public final class DroolsRuleParser {

    private static final Pattern WHEN = Pattern.compile("\\bwhen\\b", Pattern.CASE_INSENSITIVE);
    private static final Pattern THEN = Pattern.compile("\\bthen\\b", Pattern.CASE_INSENSITIVE);
    private static final Pattern BIND_VAR = Pattern.compile("^\\$?[A-Za-z_][A-Za-z0-9_]*\\s*:\\s*");
    private static final Pattern EVAL_PREFIX = Pattern.compile("^eval\\s*\\(", Pattern.CASE_INSENSITIVE);
    private static final Pattern TYPE_PREFIX = Pattern.compile("^[A-Za-z_][A-Za-z0-9_.]*\\s*\\(");

    private DroolsRuleParser() {
    }

    public static Expr parseConditions(String drl) {
        String lhs = extractLhs(drl);
        List<Clause> clauses = splitClauses(lhs);
        if (clauses.isEmpty()) {
            throw new IllegalArgumentException("No conditions found in the Drools rule's 'when' block");
        }
        Expr result = clauses.get(0).expr();
        for (int i = 1; i < clauses.size(); i++) {
            Clause clause = clauses.get(i);
            result = clause.or()
                    ? new Expr.Or(List.of(result, clause.expr()))
                    : new Expr.And(List.of(result, clause.expr()));
        }
        return result;
    }

    private record Clause(Expr expr, boolean or) {
    }

    private static String extractLhs(String drl) {
        Matcher whenM = WHEN.matcher(drl);
        if (!whenM.find()) {
            // Allow callers to pass just the LHS body directly.
            return drl;
        }
        Matcher thenM = THEN.matcher(drl);
        int end = thenM.find(whenM.end()) ? thenM.start() : drl.length();
        return drl.substring(whenM.end(), end);
    }

    private static List<Clause> splitClauses(String lhs) {
        List<Clause> clauses = new ArrayList<>();
        int pos = 0;
        int len = lhs.length();
        boolean first = true;
        while (pos < len) {
            pos = skipWhitespaceAndSeparators(lhs, pos);
            if (pos >= len) {
                break;
            }
            boolean isOr = false;
            String remainder = lhs.substring(pos);
            if (startsWithWord(remainder, "or")) {
                isOr = true;
                pos += 2;
                pos = skipWhitespace(lhs, pos);
            } else if (startsWithWord(remainder, "and")) {
                pos += 3;
                pos = skipWhitespace(lhs, pos);
            }
            if (pos >= len) {
                break;
            }

            Matcher bindM = BIND_VAR.matcher(lhs);
            bindM.region(pos, len);
            if (bindM.lookingAt()) {
                pos = bindM.end();
                pos = skipWhitespace(lhs, pos);
            }

            String rest = lhs.substring(pos);
            Matcher evalM = EVAL_PREFIX.matcher(rest);
            int clauseEnd;
            Expr clauseExpr;
            if (evalM.lookingAt()) {
                int open = pos + evalM.end() - 1;
                int close = ParenUtils.findMatchingParen(lhs, open);
                String inner = lhs.substring(open + 1, close);
                clauseExpr = BooleanExpressionParser.parse(inner);
                clauseEnd = close + 1;
            } else {
                Matcher typeM = TYPE_PREFIX.matcher(rest);
                if (!typeM.lookingAt()) {
                    throw new IllegalArgumentException(
                            "Could not parse Drools pattern starting at: '"
                                    + rest.substring(0, Math.min(40, rest.length())) + "'");
                }
                int open = pos + typeM.end() - 1;
                int close = ParenUtils.findMatchingParen(lhs, open);
                String inner = lhs.substring(open + 1, close);
                String andJoined = ParenUtils.replaceTopLevelCommasWithAnd(inner);
                clauseExpr = andJoined.isBlank() ? new Expr.BoolConst(true) : BooleanExpressionParser.parse(andJoined);
                clauseEnd = close + 1;
            }

            clauses.add(new Clause(clauseExpr, !first && isOr));
            first = false;
            pos = clauseEnd;
            pos = skipWhitespaceAndSeparators(lhs, pos);
        }
        return clauses;
    }

    private static int skipWhitespace(String s, int pos) {
        while (pos < s.length() && Character.isWhitespace(s.charAt(pos))) {
            pos++;
        }
        return pos;
    }

    private static int skipWhitespaceAndSeparators(String s, int pos) {
        while (pos < s.length() && (Character.isWhitespace(s.charAt(pos)) || s.charAt(pos) == ';')) {
            pos++;
        }
        return pos;
    }

    private static boolean startsWithWord(String s, String word) {
        if (!s.regionMatches(true, 0, word, 0, word.length())) {
            return false;
        }
        if (s.length() == word.length()) {
            return true;
        }
        char next = s.charAt(word.length());
        return Character.isWhitespace(next);
    }
}
