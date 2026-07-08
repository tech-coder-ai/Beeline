import { Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatIconModule } from '@angular/material/icon';
import { MatTooltipModule } from '@angular/material/tooltip';
import { ApiService } from '../../core/api.service';
import { ChartSpec, Dashboard, DashboardWidget, TableSpec } from '../../core/models';
import { KpiCardsComponent } from '../../shared/kpi-cards.component';
import { ResultDataViewComponent } from '../../shared/result-data-view.component';

@Component({
  selector: 'bl-dashboards-page',
  imports: [FormsModule, MatIconModule, MatTooltipModule, KpiCardsComponent, ResultDataViewComponent],
  templateUrl: './dashboards-page.component.html',
  styleUrl: './dashboards-page.component.scss',
})
export class DashboardsPageComponent implements OnInit {
  private api = inject(ApiService);

  readonly dashboards = signal<Dashboard[]>([]);
  readonly activeId = signal<string | null>(null);
  readonly active = signal<Dashboard | null>(null);
  readonly creating = signal(false);
  newName = '';

  ngOnInit(): void {
    this.load();
  }

  load(): void {
    this.api.listDashboards().subscribe((dashboards) => {
      this.dashboards.set(dashboards);
      if (!this.activeId() && dashboards.length) this.open(dashboards[0].id!);
    });
  }

  open(id: string): void {
    this.activeId.set(id);
    this.api.getDashboard(id).subscribe((d) => this.active.set(d));
  }

  startCreate(): void {
    this.creating.set(true);
    this.newName = '';
  }

  createDashboard(): void {
    if (!this.newName.trim()) return;
    this.api.createDashboard({ name: this.newName.trim() }).subscribe((d) => {
      this.creating.set(false);
      this.load();
      if (d.id) this.open(d.id);
    });
  }

  removeWidget(widget: DashboardWidget): void {
    const dash = this.active();
    if (!dash?.id || !widget.id) return;
    this.api.removeWidget(dash.id, widget.id).subscribe(() => this.open(dash.id!));
  }

  deleteDashboard(): void {
    const dash = this.active();
    if (!dash?.id) return;
    this.api.deleteDashboard(dash.id).subscribe(() => {
      this.active.set(null);
      this.activeId.set(null);
      this.load();
    });
  }

  share(): void {
    const dash = this.active();
    if (!dash?.id) return;
    this.api.getDashboard(dash.id).subscribe();
  }

  legacyTable(widget: DashboardWidget): TableSpec | null {
    if (widget.snapshot?.table?.rows?.length) return widget.snapshot.table;
    const viz = widget.visualization as { table?: TableSpec } | null | undefined;
    return viz?.table?.rows?.length ? viz.table : null;
  }

  legacyChart(widget: DashboardWidget): ChartSpec | null {
    if (widget.snapshot?.charts?.length) return widget.snapshot.charts[0];
    const viz = widget.visualization as { charts?: ChartSpec[] } | null | undefined;
    return viz?.charts?.length ? viz.charts[0] : null;
  }

  snapshotCards(widget: DashboardWidget) {
    return widget.snapshot?.cards?.length ? widget.snapshot.cards : null;
  }

  snapshotCharts(widget: DashboardWidget): ChartSpec[] {
    if (widget.snapshot?.charts?.length) return widget.snapshot.charts;
    const viz = widget.visualization as { charts?: ChartSpec[] } | null | undefined;
    return viz?.charts ?? [];
  }
}
