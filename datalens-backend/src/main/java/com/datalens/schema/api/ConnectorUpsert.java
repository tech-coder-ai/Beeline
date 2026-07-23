package com.datalens.schema.api;

import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import com.fasterxml.jackson.databind.annotation.JsonNaming;

@JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
public record ConnectorUpsert(String id, String type, String displayName, String host, int port, String username, String password, String database, String auth, String kerberosServiceName, String principal, String keytabPath, String krb5Ccache, String krb5Config, String krbHost, int connectTimeoutSeconds, java.util.List<String> allowedSchemas, java.util.List<java.util.Map<String,Object>> readReplicas, java.util.Map<String,Object> retry, java.util.Map<String,String> sessionSettings) {}
