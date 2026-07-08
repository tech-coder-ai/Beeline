import { Component, computed, inject } from '@angular/core';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import { MatTooltipModule } from '@angular/material/tooltip';
import { FeatureFlagService } from './core/feature-flags.service';
import { ThemeService } from './core/theme.service';

@Component({
  selector: 'app-root',
  imports: [RouterOutlet, RouterLink, RouterLinkActive, MatIconModule, MatTooltipModule],
  templateUrl: './app.html',
  styleUrl: './app.scss',
})
export class App {
  readonly theme = inject(ThemeService);
  private flags = inject(FeatureFlagService);

  private readonly allNavItems = [
    { path: '/chat', icon: 'forum', label: 'Chat', flag: null },
    { path: '/metadata', icon: 'schema', label: 'Metadata', flag: 'metadata_manager' as const },
    { path: '/dashboards', icon: 'dashboard', label: 'Dashboards', flag: 'dashboards' as const },
    { path: '/queries', icon: 'bookmark', label: 'Queries', flag: 'saved_queries' as const },
    { path: '/admin', icon: 'settings', label: 'Admin', flag: null },
  ];

  readonly navItems = computed(() =>
    this.allNavItems.filter((item) => !item.flag || this.flags.isEnabled(item.flag)),
  );
}
