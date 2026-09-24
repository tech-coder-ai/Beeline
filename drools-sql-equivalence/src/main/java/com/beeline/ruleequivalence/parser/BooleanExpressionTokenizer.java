package com.beeline.ruleequivalence.parser;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Tokenizes a boolean-predicate fragment shared by both the Drools LHS
 * parser (after its own preprocessing) and the SQL WHERE-predicate parser.
 * Longest-match-first ordering keeps multi-character operators (>=, <=, <>,
 * !=, ==) from being swallowed by their single-character prefixes.
 */
public final class BooleanExpressionTokenizer {

    private record Rule(Token.Type type, Pattern pattern) {
    }

    private static final List<Rule> RULES = List.of(
            new Rule(Token.Type.STRING, Pattern.compile("'(?:[^'\\\\]|\\\\.)*'|\"(?:[^\"\\\\]|\\\\.)*\"")),
            new Rule(Token.Type.NUMBER, Pattern.compile("-?\\d+(?:\\.\\d+)?")),
            new Rule(Token.Type.GTE, Pattern.compile(">=")),
            new Rule(Token.Type.LTE, Pattern.compile("<=")),
            new Rule(Token.Type.NEQ, Pattern.compile("<>|!=")),
            new Rule(Token.Type.EQ, Pattern.compile("==|=")),
            new Rule(Token.Type.LT, Pattern.compile("<")),
            new Rule(Token.Type.GT, Pattern.compile(">")),
            new Rule(Token.Type.AND, Pattern.compile("&&")),
            new Rule(Token.Type.OR, Pattern.compile("\\|\\|")),
            new Rule(Token.Type.NOT, Pattern.compile("!")),
            new Rule(Token.Type.LPAREN, Pattern.compile("\\(")),
            new Rule(Token.Type.RPAREN, Pattern.compile("\\)")),
            new Rule(Token.Type.COMMA, Pattern.compile(",")),
            new Rule(Token.Type.IDENT, Pattern.compile("[A-Za-z_][A-Za-z0-9_.$]*"))
    );

    private static final Map<String, Token.Type> KEYWORDS = Map.of(
            "and", Token.Type.AND,
            "or", Token.Type.OR,
            "not", Token.Type.NOT,
            "in", Token.Type.IN,
            "between", Token.Type.BETWEEN,
            "true", Token.Type.TRUE,
            "false", Token.Type.FALSE
    );

    private BooleanExpressionTokenizer() {
    }

    public static List<Token> tokenize(String input) {
        List<Token> tokens = new ArrayList<>();
        int pos = 0;
        int len = input.length();
        while (pos < len) {
            char c = input.charAt(pos);
            if (Character.isWhitespace(c)) {
                pos++;
                continue;
            }
            Rule matched = null;
            Matcher matcher = null;
            for (Rule rule : RULES) {
                Matcher m = rule.pattern().matcher(input);
                m.region(pos, len);
                if (m.lookingAt()) {
                    matched = rule;
                    matcher = m;
                    break;
                }
            }
            if (matched == null) {
                throw new IllegalArgumentException(
                        "Unexpected character '" + c + "' at position " + pos + " in: " + input);
            }
            String text = matcher.group();
            Token.Type type = matched.type();
            if (type == Token.Type.IDENT) {
                Token.Type keyword = KEYWORDS.get(text.toLowerCase());
                if (keyword != null) {
                    type = keyword;
                }
            }
            tokens.add(new Token(type, text));
            pos = matcher.end();
        }
        tokens.add(new Token(Token.Type.EOF, ""));
        return tokens;
    }
}
