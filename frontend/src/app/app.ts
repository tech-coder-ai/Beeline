import { Component, inject } from '@angular/core';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import { MatTooltipModule } from '@angular/material/tooltip';
import { ThemeService } from './core/theme.service';

@Component({
  selector: 'app-root',
  imports: [RouterOutlet, RouterLink, RouterLinkActive, MatIconModule, MatTooltipModule],
  templateUrl: './app.html',
  styleUrl: './app.scss',
})
export class App {
  readonly theme = inject(ThemeService);

  readonly navItems = [
    { path: '/chat', icon: 'forum', label: 'Chat' },
    { path: '/metadata', icon: 'schema', label: 'Metadata' },
    { path: '/dashboards', icon: 'dashboard', label: 'Dashboards' },
    { path: '/queries', icon: 'bookmark', label: 'Queries' },
    { path: '/admin', icon: 'settings', label: 'Admin' },
  ];
}
