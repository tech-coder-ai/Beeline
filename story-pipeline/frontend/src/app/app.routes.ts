import { Routes } from '@angular/router';

export const routes: Routes = [
  { path: '', pathMatch: 'full', redirectTo: 'overview' },
  { path: 'overview', loadComponent: () => import('./features/overview/overview').then(m => m.OverviewPage), title: 'Overview' },
  { path: 'library', loadComponent: () => import('./features/library/library').then(m => m.LibraryPage), title: 'Story library' },
  { path: 'projects', loadComponent: () => import('./features/projects/projects').then(m => m.ProjectsPage), title: 'Projects' },
  { path: 'projects/:id', loadComponent: () => import('./features/project/project').then(m => m.ProjectPage), title: 'Project' },
  { path: 'settings', loadComponent: () => import('./features/settings/settings').then(m => m.SettingsPage), title: 'Settings' },
  { path: '**', redirectTo: 'overview' },
];
