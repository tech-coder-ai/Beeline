package com.beeline.ruleequivalence.parser;

/**
 * A single lexical token. Symbolic synonyms from either dialect (Drools'
 * {@code &&}/{@code ||}/{@code !}/{@code ==} vs. SQL's {@code AND}/{@code OR}/
 * {@code NOT}/{@code =}) are folded into the same {@link Type} by the
 * tokenizer, so the parser below is dialect-agnostic.
 */
public record Token(Token.Type type, String text) {

    public enum Type {
        LPAREN, RPAREN, COMMA,
        AND, OR, NOT, IN, BETWEEN,
        EQ, NEQ, LT, LTE, GT, GTE,
        IDENT, NUMBER, STRING, TRUE, FALSE,
        EOF
    }
}
