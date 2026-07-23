package com.datalens.connectors;

import java.util.ArrayList;
import java.util.List;
import lombok.Builder;
import lombok.Value;

@Value
@Builder
public class HarvestedTable {
  String database;
  String name;
  @Builder.Default String tableType = "TABLE";
  String comment;
  String owner;
  Integer rowCount;
  Long sizeBytes;
  String storageFormat;
  String compression;
  @Builder.Default List<String> partitionColumns = new ArrayList<>();
  String lastAnalyzedAt;
  @Builder.Default List<HarvestedColumn> columns = new ArrayList<>();
}
