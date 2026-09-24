package com.beeline.ruleequivalence.ir;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

/**
 * Pretty-printer used purely for the human-readable "normalizedLeft" /
 * "normalizedRight" fields in the API response. It flattens nested And/Or
 * chains and sorts operands into a deterministic order so that two
 * structurally-equivalent trees render identically. It is NOT what the
 * equivalence verdict is based on -- that comes from semantic evaluation in
 * the engine package, which works even when the two trees are shaped
 * completely differently.
 */
public final class ExprNormalizer {

    private ExprNormalizer() {
    }

    public static String canonicalString(Expr expr) {
        return render(sort(expr));
    }

    private static Expr sort(Expr expr) {
        return switch (expr) {
            case Expr.BoolConst b -> b;
            case Expr.Comparison c -> c;
            case Expr.Not n -> new Expr.Not(sort(n.operand()));
            case Expr.And a -> new Expr.And(sortedFlatten(a.operands(), Expr.And.class));
            case Expr.Or o -> new Expr.Or(sortedFlatten(o.operands(), Expr.Or.class));
        };
    }

    private static List<Expr> sortedFlatten(List<Expr> operands, Class<? extends Expr> kind) {
        List<Expr> flat = new ArrayList<>();
        for (Expr op : operands) {
            Expr sorted = sort(op);
            if (kind.isInstance(sorted)) {
                if (sorted instanceof Expr.And a) flat.addAll(a.operands());
                else if (sorted instanceof Expr.Or o) flat.addAll(o.operands());
            } else {
                flat.add(sorted);
            }
        }
        flat.sort(Comparator.comparing(ExprNormalizer::render));
        return flat;
    }

    private static String render(Expr expr) {
        return switch (expr) {
            case Expr.BoolConst b -> Boolean.toString(b.value());
            case Expr.Comparison c -> c.field() + " " + c.op().symbol() + " " + c.value();
            case Expr.Not n -> "NOT (" + render(n.operand()) + ")";
            case Expr.And a -> "(" + String.join(" AND ", a.operands().stream().map(ExprNormalizer::render).toList()) + ")";
            case Expr.Or o -> "(" + String.join(" OR ", o.operands().stream().map(ExprNormalizer::render).toList()) + ")";
        };
    }
}
