package com.datalens.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "datalens")
public record DataLensProperties(String configPath, String apiPrefix) {}
