import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { FeatureFlagName, FeatureFlagService } from '../core/feature-flags.service';

export const featureFlagGuard = (flag: FeatureFlagName): CanActivateFn => {
  return () => {
    const flags = inject(FeatureFlagService);
    if (flags.isEnabled(flag)) return true;
    return inject(Router).createUrlTree(['/chat']);
  };
};
