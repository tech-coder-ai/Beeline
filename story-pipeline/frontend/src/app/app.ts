import { Component } from '@angular/core';
import { MatIconModule } from '@angular/material/icon';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';

@Component({
  selector: 'app-root',
  imports: [RouterOutlet, RouterLink, RouterLinkActive, MatIconModule],
  template: `
    <div class="shell">
      <nav class="rail">
        <div class="brand"><mat-icon>movie_edit</mat-icon><span>Story Studio</span></div>
        @for (item of nav; track item.path) {
          <a class="nav-item" [routerLink]="item.path" routerLinkActive="active">
            <mat-icon>{{ item.icon }}</mat-icon><span>{{ item.label }}</span>
          </a>
        }
        <div class="rail-foot">Story → YouTube pipeline</div>
      </nav>
      <main class="content"><router-outlet /></main>
    </div>
  `,
})
export class App {
  nav = [
    { path: '/overview', icon: 'dashboard', label: 'Overview' },
    { path: '/library', icon: 'menu_book', label: 'Story library' },
    { path: '/projects', icon: 'movie', label: 'Projects' },
    { path: '/settings', icon: 'tune', label: 'Settings' },
  ];
}
