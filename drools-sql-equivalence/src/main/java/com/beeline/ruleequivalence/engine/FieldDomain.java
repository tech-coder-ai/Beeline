package com.beeline.ruleequivalence.engine;

import java.util.List;

/** The finite set of "interesting" test values computed for one field. */
record FieldDomain(String field, Kind kind, List<Object> candidates) {

    enum Kind { NUMBER, STRING, BOOL }
}
