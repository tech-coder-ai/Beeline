package com.datalens.pipeline;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import lombok.Data;

@Data
public class LibraryMatchModel {
  private String entryId;
  private String question;
  private String sql;
  private double similarity;
  private List<String> tablesUsed = new ArrayList<>();
}
