package com.datalens.config;

import java.util.List;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.CorsRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class WebConfig implements WebMvcConfigurer {
  private final DataLensSettings settings;

  public WebConfig(DataLensSettings settings) { this.settings = settings; }

  @Override
  @SuppressWarnings("unchecked")
  public void addCorsMappings(CorsRegistry registry) {
    List<String> origins = (List<String>) settings.get("app.cors_origins", List.of("http://localhost:4210"));
    registry.addMapping("/**").allowedOrigins(origins.toArray(String[]::new))
        .allowedMethods("*").allowedHeaders("*").allowCredentials(true);
  }
}
