package com.datalens.config;

import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.util.Locale;

/** Converts metadata_repository.url (SQLAlchemy-style) to JDBC connection settings. */
final class MetadataRepositoryJdbc {

  record Config(
      String jdbcUrl,
      String username,
      String password,
      String driverClassName,
      int maxPoolSize) {}

  private MetadataRepositoryJdbc() {}

  static Config fromSettings(DataLensSettings settings, Path backendRoot) {
    String url = string(settings.get("metadata_repository.url", ""));
    if (url.isBlank()) {
      throw new IllegalStateException("metadata_repository.url is required in settings.yaml");
    }
    String username = string(settings.get("metadata_repository.username"));
    String password = string(settings.get("metadata_repository.password"));
    int poolSize = number(settings.get("metadata_repository.pool_size", 10));

    if (url.startsWith("jdbc:")) {
      return fromJdbc(url, username, password, poolSize);
    }
    if (url.startsWith("sqlite")) {
      return fromSqlite(url, backendRoot);
    }
    if (url.startsWith("postgresql")) {
      return fromPostgres(url, poolSize);
    }
    if (url.startsWith("oracle")) {
      return fromOracle(url, username, password, poolSize);
    }
    throw new IllegalArgumentException(
        "Unsupported metadata_repository.url scheme (use sqlite, postgresql, oracle, or jdbc): "
            + url);
  }

  private static Config fromJdbc(String url, String username, String password, int poolSize) {
    String lower = url.toLowerCase(Locale.ROOT);
    if (lower.contains("sqlite")) {
      return new Config(url, username, password, "org.sqlite.JDBC", 1);
    }
    if (lower.contains("postgresql")) {
      return new Config(url, username, password, "org.postgresql.Driver", poolSize);
    }
    if (lower.contains("oracle")) {
      return new Config(url, username, password, "oracle.jdbc.OracleDriver", poolSize);
    }
    throw new IllegalArgumentException("Unsupported JDBC metadata_repository.url: " + url);
  }

  private static Config fromSqlite(String url, Path backendRoot) {
    String path = url.replaceFirst("^sqlite\\+aiosqlite:///", "");
    if (path.startsWith("/")) {
      path = path.substring(1);
    }
    Path file = Path.of(path);
    if (!file.isAbsolute()) {
      file = backendRoot.resolve(path).normalize();
    }
    String jdbcUrl =
        "jdbc:sqlite:file:"
            + file
            + "?mode=rwc&busy_timeout=30000";
    return new Config(jdbcUrl, null, null, "org.sqlite.JDBC", 1);
  }

  private static Config fromPostgres(String url, int poolSize) {
    // postgresql+asyncpg://user:pass@host:5432/dbname
    String rest = url.replaceFirst("^postgresql\\+asyncpg://", "");
    Credentials creds = parseUserInfo(rest);
    rest = creds.remainder();

    String hostPart;
    String database;
    int slash = rest.indexOf('/');
    if (slash < 0) {
      throw new IllegalArgumentException("Invalid PostgreSQL metadata_repository.url: " + url);
    }
    hostPart = rest.substring(0, slash);
    database = rest.substring(slash + 1);
    if (database.contains("?")) {
      database = database.substring(0, database.indexOf('?'));
    }

    String jdbcUrl = "jdbc:postgresql://" + hostPart + "/" + database;
    return new Config(
        jdbcUrl,
        firstNonBlank(creds.username(), null),
        firstNonBlank(creds.password(), null),
        "org.postgresql.Driver",
        poolSize);
  }

  private static Config fromOracle(String url, String cfgUser, String cfgPass, int poolSize) {
    // oracle+oracledb://user:pass@host:1521/?service_name=ORCLPDB1
    // oracle+oracledb://user:pass@host:1521/ORCLPDB1
    String rest = url.replaceFirst("^oracle\\+(oracledb|cx_oracle)://", "");
    Credentials creds = parseUserInfo(rest);
    rest = creds.remainder();

    String query = null;
    int q = rest.indexOf('?');
    if (q >= 0) {
      query = rest.substring(q + 1);
      rest = rest.substring(0, q);
    }
    rest = rest.replaceAll("/$", "");

    String serviceName = null;
    String hostPart = rest;
    int slash = rest.indexOf('/');
    if (slash >= 0) {
      hostPart = rest.substring(0, slash);
      serviceName = rest.substring(slash + 1);
    }
    if (query != null) {
      for (String param : query.split("&")) {
        String[] kv = param.split("=", 2);
        if (kv.length == 2 && "service_name".equalsIgnoreCase(kv[0])) {
          serviceName = decode(kv[1]);
        }
      }
    }

    String jdbcUrl;
    if (serviceName != null && !serviceName.isBlank()) {
      jdbcUrl = "jdbc:oracle:thin:@//" + hostPart + "/" + serviceName;
    } else {
      jdbcUrl = "jdbc:oracle:thin:@" + hostPart;
    }

    return new Config(
        jdbcUrl,
        firstNonBlank(cfgUser, creds.username()),
        firstNonBlank(cfgPass, creds.password()),
        "oracle.jdbc.OracleDriver",
        poolSize);
  }

  private static Credentials parseUserInfo(String rest) {
    int at = rest.indexOf('@');
    if (at < 0) {
      return new Credentials(null, null, rest);
    }
    String userInfo = rest.substring(0, at);
    rest = rest.substring(at + 1);
    String username = userInfo;
    String password = null;
    int colon = userInfo.indexOf(':');
    if (colon >= 0) {
      username = decode(userInfo.substring(0, colon));
      password = decode(userInfo.substring(colon + 1));
    } else {
      username = decode(username);
    }
    return new Credentials(username, password, rest);
  }

  private record Credentials(String username, String password, String remainder) {}

  private static String decode(String value) {
    return URLDecoder.decode(value, StandardCharsets.UTF_8);
  }

  private static String string(Object value) {
    if (value == null) return null;
    String s = String.valueOf(value).trim();
    return s.isEmpty() ? null : s;
  }

  private static int number(Object value) {
    if (value instanceof Number n) return n.intValue();
    return Integer.parseInt(String.valueOf(value));
  }

  private static String firstNonBlank(String preferred, String fallback) {
    if (preferred != null && !preferred.isBlank()) return preferred;
    return fallback;
  }
}
