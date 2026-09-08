package com.datalens.service;

import com.datalens.core.exception.NotFound;
import com.datalens.core.exception.ValidationFailed;
import com.datalens.model.entity.CalculatedField;
import com.datalens.model.repository.CalculatedFieldRepository;
import com.datalens.model.repository.CatalogTableRepository;
import com.datalens.schema.api.CalculatedFieldIn;
import com.datalens.schema.api.CalculatedFieldOut;
import com.datalens.schema.api.CalculatedFieldUpdate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** CRUD for per-table calculated fields (virtual columns used in SQL generation). */
@Service
public class CalculatedFieldService {
  private final CalculatedFieldRepository fields;
  private final CatalogTableRepository tables;

  public CalculatedFieldService(CalculatedFieldRepository fields, CatalogTableRepository tables) {
    this.fields = fields;
    this.tables = tables;
  }

  public java.util.List<CalculatedFieldOut> listForTable(String tableId) {
    tables.findById(tableId).orElseThrow(() -> new NotFound("Table not found"));
    return fields.findByTableIdOrderByCreatedAtDesc(tableId).stream().map(CalculatedFieldService::toOut).toList();
  }

  @Transactional
  public CalculatedFieldOut create(CalculatedFieldIn in) {
    tables.findById(in.tableId()).orElseThrow(() -> new NotFound("Table not found"));
    String name = trim(in.name());
    String expression = trim(in.expression());
    if (name == null) throw new ValidationFailed("name must not be empty");
    if (expression == null) throw new ValidationFailed("expression must not be empty");

    CalculatedField field = new CalculatedField();
    field.setTableId(in.tableId());
    field.setName(name);
    field.setExpression(expression);
    field.setDescription(trim(in.description()));
    field.setSource("manual");
    return toOut(fields.save(field));
  }

  @Transactional
  public CalculatedFieldOut update(String id, CalculatedFieldUpdate update) {
    CalculatedField field = fields.findById(id).orElseThrow(() -> new NotFound("Calculated field not found"));
    if (update.name() != null) {
      String name = trim(update.name());
      if (name == null) throw new ValidationFailed("name must not be empty");
      field.setName(name);
    }
    if (update.expression() != null) {
      String expression = trim(update.expression());
      if (expression == null) throw new ValidationFailed("expression must not be empty");
      field.setExpression(expression);
    }
    if (update.description() != null) field.setDescription(trim(update.description()));
    if (update.isActive() != null) field.setIsActive(update.isActive());
    return toOut(fields.save(field));
  }

  @Transactional
  public void delete(String id) {
    if (!fields.existsById(id)) throw new NotFound("Calculated field not found");
    fields.deleteById(id);
  }

  private static CalculatedFieldOut toOut(CalculatedField f) {
    return new CalculatedFieldOut(
        f.getId(),
        f.getTableId(),
        f.getName(),
        f.getExpression(),
        f.getDescription(),
        !Boolean.FALSE.equals(f.getIsActive()),
        f.getSource(),
        f.getCreatedAt(),
        f.getUpdatedAt());
  }

  private static String trim(String value) {
    if (value == null) return null;
    String trimmed = value.trim();
    return trimmed.isEmpty() ? null : trimmed;
  }
}
