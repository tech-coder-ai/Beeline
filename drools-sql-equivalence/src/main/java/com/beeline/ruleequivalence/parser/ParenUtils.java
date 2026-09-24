package com.beeline.ruleequivalence.parser;

/**
 * Small text-scanning helpers used by the dialect preprocessors before the
 * shared tokenizer/parser ever sees the text: finding a matching close
 * paren and splitting a comma-separated argument list, both while
 * correctly skipping over quoted string content.
 */
final class ParenUtils {

    private ParenUtils() {
    }

    /** Returns the index of the ')' matching the '(' at {@code openIndex}. */
    static int findMatchingParen(String s, int openIndex) {
        int depth = 0;
        for (int i = openIndex; i < s.length(); i++) {
            char c = s.charAt(i);
            if (c == '\'' || c == '"') {
                i = skipQuoted(s, i);
                continue;
            }
            if (c == '(') {
                depth++;
            } else if (c == ')') {
                depth--;
                if (depth == 0) {
                    return i;
                }
            }
        }
        throw new IllegalArgumentException("Unbalanced parentheses in: " + s);
    }

    /** Given the index of an opening quote char, returns the index of its closing quote. */
    private static int skipQuoted(String s, int startIndex) {
        char quote = s.charAt(startIndex);
        int i = startIndex + 1;
        while (i < s.length()) {
            char c = s.charAt(i);
            if (c == '\\') {
                i += 2;
                continue;
            }
            if (c == quote) {
                return i;
            }
            i++;
        }
        throw new IllegalArgumentException("Unterminated quoted string in: " + s);
    }

    /** Replaces every top-level (depth-0) comma in {@code content} with " && ". */
    static String replaceTopLevelCommasWithAnd(String content) {
        StringBuilder out = new StringBuilder();
        int depth = 0;
        for (int i = 0; i < content.length(); i++) {
            char c = content.charAt(i);
            if (c == '\'' || c == '"') {
                int end = skipQuoted(content, i);
                out.append(content, i, end + 1);
                i = end;
                continue;
            }
            if (c == '(') {
                depth++;
            } else if (c == ')') {
                depth--;
            }
            if (c == ',' && depth == 0) {
                out.append(" && ");
            } else {
                out.append(c);
            }
        }
        return out.toString();
    }
}
