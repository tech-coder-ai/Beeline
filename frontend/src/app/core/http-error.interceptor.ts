import { HttpErrorResponse, HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { catchError, throwError } from 'rxjs';
import { NotificationService } from './notification.service';

/** Chat turns render their errors inline in the thread; everything else gets a toast. */
const INLINE_HANDLED = [/\/api\/v1\/chat$/];

export const httpErrorInterceptor: HttpInterceptorFn = (req, next) => {
  const notifications = inject(NotificationService);
  return next(req).pipe(
    catchError((err: unknown) => {
      if (err instanceof HttpErrorResponse && !INLINE_HANDLED.some((p) => p.test(req.url))) {
        const detail =
          (err.error && typeof err.error === 'object' && 'message' in err.error
            ? String((err.error as { message?: unknown }).message ?? '')
            : '') || err.message;
        if (err.status === 0) {
          notifications.error('Cannot reach the server', 'Check that the backend is running, then retry.');
        } else {
          notifications.error(`Request failed (${err.status})`, detail);
        }
      }
      return throwError(() => err);
    }),
  );
};
