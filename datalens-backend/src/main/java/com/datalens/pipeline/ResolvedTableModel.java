package com.datalens.pipeline;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import lombok.Data;

@Data
public class ResolvedTableModel {
  private String id;
  private String database;
  private String name;
  private String description;
  private Integer rowCount;
  private List<String> partitionColumns = new ArrayList<>();
  private List<Map<String, Object>> columns = new ArrayList<>();
  private double score;

  public String qualifiedName() {
    return database + "." + name;
  }
}
