import { Component, computed, inject, signal } from '@angular/core';
import { MatIconModule } from '@angular/material/icon';
import { FeatureFlagService } from '../../core/feature-flags.service';
import { ApprovalQueueComponent } from './approval-queue.component';
import { CatalogBrowserComponent } from './catalog-browser.component';
import { GlossaryManagerComponent } from './glossary-manager.component';
import { ImportPanelComponent } from './import-panel.component';

type Tab = 'catalog' | 'approvals' | 'glossary' | 'import';

@Component({
  selector: 'bl-metadata-page',
  imports: [MatIconModule, CatalogBrowserComponent, ApprovalQueueComponent, GlossaryManagerComponent, ImportPanelComponent],
  templateUrl: './metadata-page.component.html',
  styleUrl: './metadata-page.component.scss',
})
export class MetadataPageComponent {
  private flags = inject(FeatureFlagService);

  readonly tab = signal<Tab>('catalog');

  private readonly allTabs: { id: Tab; label: string; icon: string; flag: string | null }[] = [
    { id: 'catalog', label: 'Catalog', icon: 'schema', flag: null },
    { id: 'approvals', label: 'Approvals', icon: 'fact_check', flag: 'approvals' },
    { id: 'glossary', label: 'Glossary', icon: 'menu_book', flag: null },
    { id: 'import', label: 'Import', icon: 'upload_file', flag: 'csv_import' },
  ];

  readonly tabs = computed(() =>
    this.allTabs.filter((t) => !t.flag || this.flags.isEnabled(t.flag)),
  );
}
