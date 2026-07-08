import { Component, signal } from '@angular/core';
import { MatIconModule } from '@angular/material/icon';
import { AdminConfigComponent } from './admin-config.component';
import { AdminConnectorsComponent } from './admin-connectors.component';
import { AdminLogsComponent } from './admin-logs.component';

type Tab = 'connectors' | 'config' | 'logs';

@Component({
  selector: 'bl-admin-page',
  imports: [MatIconModule, AdminConnectorsComponent, AdminConfigComponent, AdminLogsComponent],
  templateUrl: './admin-page.component.html',
  styleUrl: './admin-page.component.scss',
})
export class AdminPageComponent {
  readonly tab = signal<Tab>('connectors');

  readonly tabs: { id: Tab; label: string; icon: string }[] = [
    { id: 'connectors', label: 'Connectors & Sync', icon: 'cable' },
    { id: 'config', label: 'Configuration', icon: 'tune' },
    { id: 'logs', label: 'Logs & Analytics', icon: 'monitoring' },
  ];
}
