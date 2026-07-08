import { Component, signal } from '@angular/core';
import { MatIconModule } from '@angular/material/icon';
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
  readonly tab = signal<Tab>('catalog');

  readonly tabs: { id: Tab; label: string; icon: string }[] = [
    { id: 'catalog', label: 'Catalog', icon: 'schema' },
    { id: 'approvals', label: 'Approvals', icon: 'fact_check' },
    { id: 'glossary', label: 'Glossary', icon: 'menu_book' },
    { id: 'import', label: 'Import', icon: 'upload_file' },
  ];
}
