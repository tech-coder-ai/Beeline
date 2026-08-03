package com.datalens.config;

import com.zaxxer.hikari.HikariDataSource;
import java.nio.file.Path;
import javax.sql.DataSource;
import org.springframework.boot.autoconfigure.orm.jpa.HibernatePropertiesCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;

/**
 * Metadata store connection is driven by {@code metadata_repository} in settings.yaml
 * (same file as the Python backend). Change {@code metadata_repository.url} to switch
 * between SQLite, PostgreSQL, and Oracle without code changes.
 */
@Configuration
public class MetadataRepositoryConfig {

  @Bean
  @Primary
  DataSource metadataDataSource(DataLensProperties props, DataLensSettings settings) {
    Path configPath = Path.of(props.configPath()).toAbsolutePath().normalize();
    Path backendRoot = configPath.getParent().getParent();
    MetadataRepositoryJdbc.Config jdbc = MetadataRepositoryJdbc.fromSettings(settings, backendRoot);

    HikariDataSource ds = new HikariDataSource();
    ds.setPoolName("metadata-repository");
    ds.setJdbcUrl(jdbc.jdbcUrl());
    ds.setDriverClassName(jdbc.driverClassName());
    if (jdbc.username() != null) {
      ds.setUsername(jdbc.username());
    }
    if (jdbc.password() != null) {
      ds.setPassword(jdbc.password());
    }
    ds.setMaximumPoolSize(jdbc.maxPoolSize());
    return ds;
  }

  @Bean
  HibernatePropertiesCustomizer metadataHibernateProperties(DataLensSettings settings) {
    return props -> {
      String url = String.valueOf(settings.get("metadata_repository.url", ""));
      if (url.contains("sqlite")) {
        props.put("hibernate.dialect", "org.hibernate.community.dialect.SQLiteDialect");
      }
      props.put("hibernate.jdbc.time_zone", "UTC");
    };
  }
}
