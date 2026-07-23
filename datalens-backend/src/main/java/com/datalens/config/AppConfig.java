package com.datalens.config;

import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration
@EnableConfigurationProperties(DataLensProperties.class)
@org.springframework.data.jpa.repository.config.EnableJpaRepositories(basePackages = "com.datalens.model.repository")
public class AppConfig {
  @Bean
  RestClient.Builder restClientBuilder() {
    return RestClient.builder();
  }
}
