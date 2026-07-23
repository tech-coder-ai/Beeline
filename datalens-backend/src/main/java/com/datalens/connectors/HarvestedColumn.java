package com.datalens.connectors;

import lombok.Builder;
import lombok.Value;

@Value
@Builder
public class HarvestedColumn {
  String name;
  String dataType;
  String comment;
  @Builder.Default boolean partition = false;
  @Builder.Default int position = 0;
}
