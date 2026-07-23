package com.datalens.config;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import org.springframework.stereotype.Component;
import org.yaml.snakeyaml.Yaml;

@Component
public class DataLensSettings {
  private static final Pattern ENV = Pattern.compile("\$\{([A-Za-z_][A-Za-z0-9_]*)\}");
  private static final Pattern OVERRIDE = Pattern.compile("^DATALENS__(.+)$");

  private final DataLensProperties properties;
  private final Map<String, Object> raw;

  public DataLensSettings(DataLensProperties props) throws IOException {
    this.properties = props;
    Path path = Path.of(props.configPath()).toAbsolutePath().normalize();
    Yaml yaml = new Yaml();
    @SuppressWarnings("unchecked")
    Map<String, Object> loaded = yaml.load(Files.readString(path));
    this.raw = expandEnv(loaded == null ? new LinkedHashMap<>() : loaded);
    applyEnvOverrides(this.raw);
  }

  @SuppressWarnings("unchecked")
  public Map<String, Object> raw() { return raw; }

  @SuppressWarnings("unchecked")
  public Map<String, Object> section(String dotPath) {
    Object node = get(dotPath);
    return node instanceof Map ? (Map<String, Object>) node : Map.of();
  }

  public Object get(String dotPath, Object defaultValue) {
    Object v = get(dotPath);
    return v == null ? defaultValue : v;
  }

  public Object get(String dotPath) {
    String[] parts = dotPath.split("\.");
    Object node = raw;
    for (String p : parts) {
      if (!(node instanceof Map<?, ?> m) || !m.containsKey(p)) return null;
      node = m.get(p);
    }
    return node;
  }

  public void persistConnectorDefinitions(Map<String, Object> definitions) throws IOException {
    persistConnectorDefinitions(definitions, null);
  }

  @SuppressWarnings("unchecked")
  public void persistConnectorDefinitions(Map<String, Object> definitions, String defaultId) throws IOException {
    Path path = Path.of(properties.configPath()).toAbsolutePath().normalize();
    Yaml yaml = new Yaml();
    @SuppressWarnings("unchecked")
    Map<String, Object> data = yaml.load(Files.readString(path.toAbsolutePath().normalize()));
    if (data == null) data = new LinkedHashMap<>();
    Map<String, Object> connectors = (Map<String, Object>) data.computeIfAbsent("connectors", k -> new LinkedHashMap<>());
    connectors.put("definitions", definitions);
    if (defaultId != null) connectors.put("default", defaultId);
    Files.writeString(path.toAbsolutePath().normalize(), yaml.dump(data));
  }

  private static Object expandEnv(Object value) {
    if (value instanceof String s) {
      Matcher m = ENV.matcher(s);
      StringBuffer sb = new StringBuffer();
      while (m.find()) {
        m.appendReplacement(sb, Matcher.quoteReplacement(System.getenv().getOrDefault(m.group(1), "")));
      }
      m.appendTail(sb);
      return sb.toString();
    }
    if (value instanceof Map<?, ?> map) {
      Map<String, Object> out = new LinkedHashMap<>();
      map.forEach((k, v) -> out.put(String.valueOf(k), expandEnv(v)));
      return out;
    }
    if (value instanceof Iterable<?> it) {
      return it.stream().map(DataLensSettings::expandEnv).toList();
    }
    return value;
  }

  @SuppressWarnings("unchecked")
  private static void applyEnvOverrides(Map<String, Object> root) {
    for (Map.Entry<String, String> e : System.getenv().entrySet()) {
      Matcher m = OVERRIDE.matcher(e.getKey());
      if (!m.matches()) continue;
      String[] parts = m.group(1).toLowerCase().split("__");
      Map<String, Object> node = root;
      for (int i = 0; i < parts.length - 1; i++) {
        node = (Map<String, Object>) node.computeIfAbsent(parts[i], k -> new LinkedHashMap<>());
      }
      node.put(parts[parts.length - 1], coerce(e.getValue()));
    }
  }

  private static Object coerce(String raw) {
    if ("true".equalsIgnoreCase(raw) || "false".equalsIgnoreCase(raw)) return Boolean.parseBoolean(raw);
    try { return Integer.parseInt(raw); } catch (NumberFormatException ignored) {}
    try { return Double.parseDouble(raw); } catch (NumberFormatException ignored) {}
    return raw;
  }
}
