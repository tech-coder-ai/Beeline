import { Routes } from '@angular/router';
import { featureFlagGuard } from './core/feature-flag.guard';

export const routes: Routes = [
  { path: '', pathMatch: 'full', redirectTo: 'chat' },
  {
    path: 'chat',
    loadComponent: () =>
      import('./features/chat/chat-page.component').then((m) => m.ChatPageComponent),
  },
  {
    path: 'metadata',
    canActivate: [featureFlagGuard('metadata_manager')],
    loadComponent: () =>
      import('./features/metadata/metadata-page.component').then((m) => m.MetadataPageComponent),
  },
  {
    path: 'dashboards',
    canActivate: [featureFlagGuard('dashboards')],
    loadComponent: () =>
      import('./features/dashboards/dashboards-page.component').then(
        (m) => m.DashboardsPageComponent,
      ),
  },
  {
    path: 'queries',
    canActivate: [featureFlagGuard('saved_queries')],
    loadComponent: () =>
      import('./features/queries/queries-page.component').then((m) => m.QueriesPageComponent),
  },
  {
    path: 'admin',
    loadComponent: () =>
      import('./features/admin/admin-page.component').then((m) => m.AdminPageComponent),
  },
  { path: '**', redirectTo: 'chat' },
];
