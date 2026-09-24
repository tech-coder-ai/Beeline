package com.beeline.ruleequivalence.ir;

public enum Op {
    EQ("="), NEQ("!="), LT("<"), LTE("<="), GT(">"), GTE(">=");

    private final String symbol;

    Op(String symbol) {
        this.symbol = symbol;
    }

    public String symbol() {
        return symbol;
    }
}
