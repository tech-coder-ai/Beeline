import { DatePipe } from '@angular/common';
import { Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatIconModule } from '@angular/material/icon';
import { MatTooltipModule } from '@angular/material/tooltip';
import { ApiService } from '../../core/api.service';
import { ConnectorInfo, ConnectorService } from '../../core/connector.service';
import { SyncRun } from '../../core/models';

type ConnectorAuth = 'NONE' | 'NOSASL' | 'LDAP' | 'KERBEROS';

interface ConnectorForm {
  id: string;
  type: string;
  display_name: string;
  host: string;
  port: number;
  username: string;
  password: string;
  database: string;
  auth: ConnectorAuth;
  kerberos_service_name: string;
  principal: string;
  keytab_path: string;
  krb5_ccache: string;
  krb5_config: string;
  krb_host: string;
}

@Component({
  selector: 'bl-admin-connectors',
  imports: [DatePipe, FormsModule, MatIconModule, MatTooltipModule],
  templateUrl: './admin-connectors.component.html',
  styleUrl: './admin-connectors.component.scss',
})
export class AdminConnectorsComponent implements OnInit {
  private api = inject(ApiService);
  readonly connectorService = inject(ConnectorService);

  readonly connectors = signal<ConnectorInfo[]>([]);
  readonly defaultId = signal<string>('');
  readonly testResults = signal<Record<string, { ok: boolean; message: string; latency_ms: number }>>({});
  readonly testing = signal<string | null>(null);
  readonly syncRuns = signal<SyncRun[]>([]);
  readonly syncing = signal(false);
  readonly enriching = signal(false);
  readonly saving = signal(false);
  readonly showForm = signal(false);
  readonly editingId = signal<string | null>(null);
  readonly syncConnectorId = signal<string | null>(null);

  form: ConnectorForm = this.emptyForm();

  ngOnInit(): void {
    this.load();
    this.loadRuns();
    this.connectorService.load();
  }

  emptyForm(): ConnectorForm {
    return {
      id: '',
      type: 'hive',
      display_name: '',
      host: 'localhost',
      port: 10000,
      username: 'hive',
      password: '',
      database: 'default',
      auth: 'NONE',
      kerberos_service_name: 'hive',
      principal: '',
      keytab_path: '',
      krb5_ccache: '',
      krb5_config: '',
      krb_host: '',
    };
  }

  load(): void {
    this.api.getConnectors().subscribe((res) => {
      this.connectors.set(res.connectors as ConnectorInfo[]);
      this.defaultId.set(res.default);
    });
  }

  loadRuns(): void {
    this.api.listSyncRuns().subscribe((runs) => this.syncRuns.set(runs));
  }

  openNewForm(): void {
    this.editingId.set(null);
    this.form = { ...this.emptyForm(), display_name: 'New Hive connection' };
    this.showForm.set(true);
  }

  openEditForm(connector: ConnectorInfo): void {
    this.editingId.set(connector.id);
    this.form = {
      id: connector.id,
      type: String(connector.type ?? 'hive'),
      display_name: String(connector.display_name ?? connector.id),
      host: String(connector.host ?? 'localhost'),
      port: Number(connector.port ?? 10000),
      username: String(connector['username'] ?? 'hive'),
      password: '',
      database: String(connector.database ?? 'default'),
      auth: (String(connector['auth'] ?? 'NONE').toUpperCase() as ConnectorAuth),
      kerberos_service_name: String(connector['kerberos_service_name'] ?? 'hive'),
      principal: String(connector['principal'] ?? connector['username'] ?? ''),
      keytab_path: String(connector['keytab_path'] ?? ''),
      krb5_ccache: String(connector['krb5_ccache'] ?? ''),
      krb5_config: String(connector['krb5_config'] ?? connector['krb5_conf'] ?? ''),
      krb_host: String(connector['krb_host'] ?? ''),
    };
    this.showForm.set(true);
  }

  cancelForm(): void {
    this.showForm.set(false);
    this.editingId.set(null);
  }

  isKerberos(): boolean {
    return this.form.auth === 'KERBEROS';
  }

  isLdap(): boolean {
    return this.form.auth === 'LDAP';
  }

  showUsername(): boolean {
    return this.form.auth === 'LDAP' || this.form.auth === 'NONE';
  }

  usernameLabel(): string {
    if (this.form.auth === 'KERBEROS') return 'Principal (optional hint)';
    if (this.form.auth === 'LDAP') return 'Username';
    return 'Username (optional)';
  }

  authHelp(): string {
    switch (this.form.auth) {
      case 'KERBEROS':
        return 'Kerberos uses tickets from keytab/kinit on the Beeline backend host. Set krb5.conf (or krb5.ini on Windows), service name, and principal; optionally point at a keytab or credential cache file.';
      case 'LDAP':
        return 'LDAP requires a username and password for HiveServer2.';
      case 'NOSASL':
        return 'NOSASL uses a raw socket with no SASL negotiation. Password is not used.';
      default:
        return 'NONE is Hive\'s default SASL PLAIN mode with unchecked credentials.';
    }
  }

  buildPayload(): Record<string, unknown> {
    const base: Record<string, unknown> = {
      id: this.form.id.trim(),
      type: this.form.type,
      display_name: this.form.display_name,
      host: this.form.host,
      port: this.form.port,
      database: this.form.database,
      auth: this.form.auth,
    };

    if (this.form.auth === 'LDAP') {
      base['username'] = this.form.username;
      if (this.form.password) base['password'] = this.form.password;
    } else if (this.form.auth === 'KERBEROS') {
      base['kerberos_service_name'] = this.form.kerberos_service_name || 'hive';
      base['principal'] = this.form.principal;
      base['username'] = this.form.principal || this.form.username;
      base['keytab_path'] = this.form.keytab_path;
      base['krb5_ccache'] = this.form.krb5_ccache;
      base['krb5_config'] = this.form.krb5_config;
      base['krb_host'] = this.form.krb_host;
      base['host'] = this.form.host;
    } else if (this.form.auth === 'NONE') {
      base['username'] = this.form.username;
    } else if (this.form.auth === 'NOSASL') {
      base['username'] = this.form.username;
    }

    return base;
  }

  saveConnector(): void {
    const id = this.form.id.trim();
    if (!id) return;
    this.saving.set(true);
    this.api.upsertConnector(this.buildPayload()).subscribe({
      next: () => {
        this.saving.set(false);
        this.showForm.set(false);
        this.load();
        this.connectorService.load();
      },
      error: () => this.saving.set(false),
    });
  }

  setDefault(connectorId: string): void {
    this.connectorService.setDefault(connectorId);
    setTimeout(() => this.load(), 300);
  }

  test(connectorId: string): void {
    this.testing.set(connectorId);
    this.api.testConnector(connectorId).subscribe({
      next: (result) => {
        this.testResults.update((r) => ({ ...r, [connectorId]: result }));
        this.testing.set(null);
      },
      error: (err) => {
        this.testResults.update((r) => ({
          ...r,
          [connectorId]: { ok: false, message: err?.error?.message ?? 'Test failed', latency_ms: 0 },
        }));
        this.testing.set(null);
      },
    });
  }

  triggerSync(mode: 'full' | 'incremental', connectorId?: string): void {
    this.syncing.set(true);
    this.syncConnectorId.set(connectorId ?? null);
    this.api.triggerSync(mode, connectorId).subscribe({
      next: () => {
        this.syncing.set(false);
        this.syncConnectorId.set(null);
        setTimeout(() => this.loadRuns(), 1500);
      },
      error: () => {
        this.syncing.set(false);
        this.syncConnectorId.set(null);
      },
    });
  }

  triggerEnrichment(): void {
    this.enriching.set(true);
    this.api.triggerEnrichment().subscribe({
      next: () => this.enriching.set(false),
      error: () => this.enriching.set(false),
    });
  }
}
