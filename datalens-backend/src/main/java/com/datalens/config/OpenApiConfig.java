package com.datalens.config;

import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.info.Info;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OpenApiConfig {

  @Bean
  OpenAPI dataLensOpenApi() {
    return new OpenAPI()
        .info(
            new Info()
                .title("DataLens API")
                .description("Enterprise NL-to-SQL analytics & metadata platform")
                .version("1.0.0"));
  }
}
