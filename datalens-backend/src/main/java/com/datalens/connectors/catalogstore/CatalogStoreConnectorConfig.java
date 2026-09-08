package com.datalens.connectors.catalogstore;

import com.datalens.config.DataLensProperties;
import com.datalens.config.DataLensSettings;
import com.datalens.config.MetadataRepositoryJdbc;
import com.datalens.connectors.ConnectorRegistry;
import com.zaxxer.hikari.HikariDataSource;
import java.nio.file.Path;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/**
 * Registers a "catalog_store" connector type pointed at the SAME database as
 * metadata_repository.url, but through its own small connection pool - never the
 * {@code @Primary} datasource Hibernate uses for the app's own JPA entities, so ad-hoc chat
 * queries can't contend with live app traffic or an in-flight transaction on that pool.
 */
@Configuration
public class CatalogStoreConnectorConfig {

  @Bean
  HikariDataSource catalogStoreDataSource(DataLensProperties properties, DataLensSettings settings) {
    Path configPath = Path.of(properties.configPath()).toAbsolutePath().normalize();
    Path backendRoot = configPath.getParent().getParent();
    MetadataRepositoryJdbc.Config jdbc = MetadataRepositoryJdbc.fromSettings(settings, backendRoot);

    HikariDataSource ds = new HikariDataSource();
    ds.setPoolName("catalog-store-connector");
    ds.setJdbcUrl(jdbc.jdbcUrl());
    ds.setDriverClassName(jdbc.driverClassName());
    if (jdbc.username() != null) ds.setUsername(jdbc.username());
    if (jdbc.password() != null) ds.setPassword(jdbc.password());
    // Deliberately small and separate from the app's own JPA pool (which may itself be
    // constrained to 1 connection for sqlite) - this only ever serves occasional, small,
    // read-only governance queries.
    ds.setMaximumPoolSize(Math.min(jdbc.maxPoolSize(), 2));
    ds.setReadOnly(true);
    return ds;
  }

  @Bean
  ApplicationRunner registerCatalogStoreConnectorType(ConnectorRegistry registry, HikariDataSource catalogStoreDataSource) {
    return args ->
        registry.register(
            "catalog_store",
            (connectorId, config) ->
                new CatalogStoreAnalyticsConnector(
                    connectorId, config, catalogStoreDataSource, catalogStoreDataSource.getDriverClassName()));
  }
}
