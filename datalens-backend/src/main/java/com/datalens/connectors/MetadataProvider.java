package com.datalens.connectors;

import java.util.List;

public interface MetadataProvider {
  List<String> listDatabases() throws Exception;

  List<String> listTables(String database) throws Exception;

  HarvestedTable describeTable(String database, String table) throws Exception;
}
