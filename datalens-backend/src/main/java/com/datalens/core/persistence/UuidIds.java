package com.datalens.core.persistence;

import java.util.UUID;

public final class UuidIds {
  private UuidIds() {}
  public static String newId() { return UUID.randomUUID().toString().replace("-", ""); }
}
