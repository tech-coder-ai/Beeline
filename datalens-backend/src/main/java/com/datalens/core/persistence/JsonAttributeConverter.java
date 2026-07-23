package com.datalens.core.persistence;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;
import jakarta.persistence.AttributeConverter;
import jakarta.persistence.Converter;

@Converter
public class JsonAttributeConverter implements AttributeConverter<Object, String> {
  private static final ObjectMapper MAPPER = new ObjectMapper()
      .registerModule(new JavaTimeModule())
      .setPropertyNamingStrategy(PropertyNamingStrategies.SNAKE_CASE);

  @Override
  public String convertToDatabaseColumn(Object attribute) {
    if (attribute == null) return null;
    try { return MAPPER.writeValueAsString(attribute); }
    catch (Exception e) { throw new IllegalStateException(e); }
  }

  @Override
  public Object convertToEntityAttribute(String dbData) {
    if (dbData == null || dbData.isBlank()) return null;
    try { return MAPPER.readValue(dbData, new TypeReference<>() {}); }
    catch (Exception e) { return dbData; }
  }
}
