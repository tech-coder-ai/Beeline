package com.beeline.ruleequivalence.parser;

import com.beeline.ruleequivalence.ir.Expr;
import com.beeline.ruleequivalence.ir.Literal;
import com.beeline.ruleequivalence.ir.Op;

import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;

/**
 * Recursive-descent parser for the boolean-predicate grammar shared by both
 * dialects, over the dialect-normalized token stream produced by
 * {@link BooleanExpressionTokenizer}:
 *
 * <pre>
 *   expr       := orExpr
 *   orExpr     := andExpr (OR andExpr)*
 *   andExpr    := notExpr (AND notExpr)*
 *   notExpr    := NOT notExpr | primary
 *   primary    := LPAREN expr RPAREN | TRUE | FALSE | comparison
 *   comparison := IDENT compOp literal
 *              |  IDENT IN LPAREN literal (COMMA literal)* RPAREN
 *              |  IDENT BETWEEN literal AND literal
 * </pre>
 *
 * Comparisons are always field-vs-literal, never field-vs-field -- that
 * restriction is what makes the equivalence engine's critical-value check
 * exact rather than merely a heuristic.
 */
public final class BooleanExpressionParser {

    private final List<Token> tokens;
    private int pos = 0;

    private BooleanExpressionParser(List<Token> tokens) {
        this.tokens = tokens;
    }

    public static Expr parse(String input) {
        if (input == null || input.isBlank()) {
            throw new IllegalArgumentException("Cannot parse an empty predicate");
        }
        BooleanExpressionParser parser = new BooleanExpressionParser(BooleanExpressionTokenizer.tokenize(input));
        Expr expr = parser.parseOr();
        parser.expect(Token.Type.EOF);
        return expr;
    }

    private Expr parseOr() {
        Expr left = parseAnd();
        if (peek().type() != Token.Type.OR) {
            return left;
        }
        List<Expr> operands = new ArrayList<>();
        operands.add(left);
        while (peek().type() == Token.Type.OR) {
            advance();
            operands.add(parseAnd());
        }
        return new Expr.Or(operands);
    }

    private Expr parseAnd() {
        Expr left = parseNot();
        if (peek().type() != Token.Type.AND) {
            return left;
        }
        List<Expr> operands = new ArrayList<>();
        operands.add(left);
        while (peek().type() == Token.Type.AND) {
            advance();
            operands.add(parseNot());
        }
        return new Expr.And(operands);
    }

    private Expr parseNot() {
        if (peek().type() == Token.Type.NOT) {
            advance();
            return new Expr.Not(parseNot());
        }
        return parsePrimary();
    }

    private Expr parsePrimary() {
        Token t = peek();
        if (t.type() == Token.Type.LPAREN) {
            advance();
            Expr inner = parseOr();
            expect(Token.Type.RPAREN);
            return inner;
        }
        if (t.type() == Token.Type.TRUE) {
            advance();
            return new Expr.BoolConst(true);
        }
        if (t.type() == Token.Type.FALSE) {
            advance();
            return new Expr.BoolConst(false);
        }
        return parseComparison();
    }

    private Expr parseComparison() {
        Token fieldTok = expect(Token.Type.IDENT);
        String field = fieldTok.text();
        Token opTok = peek();
        return switch (opTok.type()) {
            case IN -> {
                advance();
                yield parseInClause(field);
            }
            case BETWEEN -> {
                advance();
                yield parseBetweenClause(field);
            }
            case EQ, NEQ, LT, LTE, GT, GTE -> {
                advance();
                Literal value = parseLiteral();
                yield new Expr.Comparison(field, mapOp(opTok.type()), value);
            }
            default -> throw new IllegalArgumentException(
                    "Expected a comparison operator after field '" + field + "' but found '" + opTok.text() + "'");
        };
    }

    private Expr parseInClause(String field) {
        expect(Token.Type.LPAREN);
        List<Expr> equalities = new ArrayList<>();
        equalities.add(new Expr.Comparison(field, Op.EQ, parseLiteral()));
        while (peek().type() == Token.Type.COMMA) {
            advance();
            equalities.add(new Expr.Comparison(field, Op.EQ, parseLiteral()));
        }
        expect(Token.Type.RPAREN);
        return equalities.size() == 1 ? equalities.get(0) : new Expr.Or(equalities);
    }

    private Expr parseBetweenClause(String field) {
        Literal lo = parseLiteral();
        expect(Token.Type.AND);
        Literal hi = parseLiteral();
        return new Expr.And(List.of(
                new Expr.Comparison(field, Op.GTE, lo),
                new Expr.Comparison(field, Op.LTE, hi)));
    }

    private Literal parseLiteral() {
        Token t = advance();
        return switch (t.type()) {
            case NUMBER -> new Literal.NumberLiteral(new BigDecimal(t.text()));
            case STRING -> new Literal.StringLiteral(unquote(t.text()));
            case TRUE -> new Literal.BoolLiteral(true);
            case FALSE -> new Literal.BoolLiteral(false);
            default -> throw new IllegalArgumentException("Expected a literal value but found '" + t.text() + "'");
        };
    }

    private static Op mapOp(Token.Type type) {
        return switch (type) {
            case EQ -> Op.EQ;
            case NEQ -> Op.NEQ;
            case LT -> Op.LT;
            case LTE -> Op.LTE;
            case GT -> Op.GT;
            case GTE -> Op.GTE;
            default -> throw new IllegalStateException("Not a comparison operator: " + type);
        };
    }

    private static String unquote(String raw) {
        String inner = raw.substring(1, raw.length() - 1);
        char quote = raw.charAt(0);
        return inner.replace("\\" + quote, String.valueOf(quote)).replace("\\\\", "\\");
    }

    private Token peek() {
        return tokens.get(pos);
    }

    private Token advance() {
        return tokens.get(pos++);
    }

    private Token expect(Token.Type type) {
        Token t = peek();
        if (t.type() != type) {
            throw new IllegalArgumentException("Expected " + type + " but found '" + t.text() + "'");
        }
        return advance();
    }
}
